"""Execute the exact Run methods from a frozen source against faults and Docker.

Celery registration, storage and remote submission APIs are isolated here.
Container execution is real when REAL_DOCKER=1. This is builder-owned testing.
"""
import ast
import asyncio
import copy
import json
import logging
import math
import os
from pathlib import Path
import signal
import threading
import time
from types import SimpleNamespace

import pytest


class APIError(Exception):
    pass


class NotFound(APIError):
    pass


def load_subject(client):
    path = Path(os.getenv('WORKER_SUBJECT', 'worker_builder_baseline.py'))
    tree = ast.parse(path.read_text())
    body = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in {
            'ProgramKind', 'SubmissionStatus', 'SubmissionException', 'ExecutionTimeLimitExceeded', 'Run',
        }:
            node = copy.deepcopy(node)
            if node.name == 'Run':
                node.body = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                             and n.name in {'_run_container_engine_cmd', 'start'}]
                node.decorator_list = []
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == 'alarm_handler':
            body.append(copy.deepcopy(node))
    docker = (SimpleNamespace(errors=SimpleNamespace(APIError=APIError, NotFound=NotFound))
              if not os.getenv('REAL_DOCKER') else __import__('docker'))
    namespace = dict(asyncio=asyncio, threading=threading, time=time, math=math, os=os,
                     json=json, signal=signal, client=client, docker=docker,
                     requests=SimpleNamespace(exceptions=SimpleNamespace(ReadTimeout=TimeoutError)),
                     logger=logging.getLogger('worker-court'),
                     Settings=SimpleNamespace(COMPUTE_WORKER_DISABLE_LOG_UPLOAD=True,
                                              LOG_LEVEL='INFO', LOG_LEVEL_DEBUG='debug'))
    exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), str(path), 'exec'), namespace)
    return namespace


def make_run(namespace, limit=0.15):
    run = namespace['Run'].__new__(namespace['Run'])
    run.execution_time_limit = limit
    run._execution_deadline = None
    run._execution_time_limit_exceeded = threading.Event()
    run.logs = {}
    run.completed_program_counter = 0
    run.stdout, run.stderr = 'stdout', 'stderr'
    run.ingestion_stdout, run.ingestion_stderr = 'ingestion_stdout', 'ingestion_stderr'
    run.websocket_url = 'ws://localhost/unused'
    return run


class FaultClient:
    def __init__(self, lifetime=0.5, chunks=(), start_delay=0, wait_delay=0):
        self.lifetime, self.chunks = lifetime, list(chunks)
        self.start_delay, self.wait_delay = start_delay, wait_delay
        self.started = None
        self.removed = threading.Event()
        self.removals = []

    def start(self, container):
        self.started = time.monotonic()
        if self.start_delay:
            self.removed.wait(self.start_delay)

    def attach(self, container, **kwargs):
        for chunk in self.chunks:
            yield chunk
        self.removed.wait(self.lifetime)

    def inspect_container(self, container):
        return {'State': {'Status': 'running'}}

    def wait(self, container):
        if self.wait_delay:
            self.removed.wait(self.wait_delay)
        if self.removed.is_set():
            raise NotFound('removed')
        return {'StatusCode': 0}

    def remove_container(self, container, **kwargs):
        self.removals.append(container if isinstance(container, str) else container['Id'])
        self.removed.set()


async def observed_execution(run, kind, container):
    ticks = []
    stop = asyncio.Event()

    async def heartbeat():
        while not stop.is_set():
            ticks.append(time.monotonic())
            await asyncio.sleep(0.005)

    heart = asyncio.create_task(heartbeat())
    before = time.monotonic()
    try:
        await run._run_container_engine_cmd(container, kind)
    finally:
        stop.set()
        await heart
    return time.monotonic() - before, ticks


def test_quiet_container_is_stopped_at_deadline():
    client = FaultClient()
    ns = load_subject(client)
    run = make_run(ns, 0.08)
    elapsed, _ = asyncio.run(observed_execution(run, ns['ProgramKind'].SCORING_PROGRAM, {'Id': 'quiet-id'}))
    assert run._execution_time_limit_exceeded.is_set()
    assert elapsed < 0.35
    assert client.removals and set(client.removals) == {'quiet-id'}


def test_event_loop_progresses_during_blocking_log_stream():
    client = FaultClient()
    ns = load_subject(client)
    run = make_run(ns, 0.15)
    _, ticks = asyncio.run(observed_execution(run, ns['ProgramKind'].SCORING_PROGRAM, {'Id': 'heartbeat-id'}))
    assert len(ticks) >= 10
    assert max(b - a for a, b in zip(ticks, ticks[1:])) < 0.1


@pytest.mark.parametrize('phase', ['start', 'wait'])
def test_watchdog_unblocks_other_blocking_engine_calls(phase):
    client = FaultClient(lifetime=0, start_delay=0.5 if phase == 'start' else 0,
                         wait_delay=0.5 if phase == 'wait' else 0)
    ns = load_subject(client)
    run = make_run(ns, 0.08)
    elapsed, ticks = asyncio.run(observed_execution(run, ns['ProgramKind'].SCORING_PROGRAM, {'Id': 'call-id'}))
    assert elapsed < 0.35
    assert run._execution_time_limit_exceeded.is_set()
    assert len(ticks) >= 5


def test_normal_completion_cancels_watchdog_and_keeps_both_streams():
    client = FaultClient(lifetime=0.01, chunks=[(b'out\n', b'err\n')])
    ns = load_subject(client)
    run = make_run(ns, 0.1)
    kind = ns['ProgramKind'].SCORING_PROGRAM
    asyncio.run(run._run_container_engine_cmd({'Id': 'completed-id'}, kind))
    count = len(client.removals)
    time.sleep(0.13)
    assert len(client.removals) == count
    assert not run._execution_time_limit_exceeded.is_set()
    assert run.logs[kind]['returncode'] == 0
    assert run.logs[kind]['stdout']['data'] == b'out\n'
    assert run.logs[kind]['stderr']['data'] == b'err\n'


def test_cancelled_task_cleans_container_and_watchdog():
    client = FaultClient(lifetime=0.8)
    ns = load_subject(client)
    run = make_run(ns, 0.4)

    async def trial():
        task = asyncio.create_task(run._run_container_engine_cmd({'Id': 'cancelled-id'}, ns['ProgramKind'].SCORING_PROGRAM))
        await asyncio.sleep(0.025)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(trial())
    count = len(client.removals)
    time.sleep(0.45)
    assert count > 0
    assert len(client.removals) == count
    assert not run._execution_time_limit_exceeded.is_set()


def test_start_reports_timeout_instead_of_generic_failure():
    client = FaultClient()
    ns = load_subject(client)
    run = make_run(ns, 0.08)
    run.is_scoring, run.human_in_the_loop = True, True
    run.ingestion_only_during_scoring = False
    run.root_dir = '/tmp/worker-court'
    run.watch = True
    run.ingestion_program_container_name = 'ingestion-name'
    run.scoring_program_container_name = 'scoring-name'
    updates = []
    run._update_submission = lambda data: updates.append(data)
    run._update_status = lambda *args, **kwargs: None

    async def program(kind, program_dir):
        return await run._run_container_engine_cmd({'Id': 'classification-id'}, kind)

    async def send(message):
        return None

    run._run_program_directory = program
    run._send_data_through_socket = send
    with pytest.raises(ns['SubmissionException'], match='Execution Time Limit exceeded'):
        run.start()
    assert updates[0]['type'] == 'Execution_Time_Limit_Exceeded'


@pytest.mark.skipif(not os.getenv('REAL_DOCKER'), reason='Real Docker court runs on GitHub')
@pytest.mark.parametrize('command', [
    ['sh', '-c', 'sleep 3'],
    ['sh', '-c', 'while true; do echo out; echo err >&2; sleep 0.02; done'],
])
def test_real_docker_deadline_and_event_loop(command):
    import docker
    client = docker.APIClient(base_url='unix:///var/run/docker.sock', timeout=8)
    ns = load_subject(client)
    run = make_run(ns, 0.5)
    container = client.create_container(os.environ['WORKER_TEST_IMAGE'], command=command, network_disabled=True)
    try:
        elapsed, ticks = asyncio.run(observed_execution(run, ns['ProgramKind'].SCORING_PROGRAM, container))
        assert run._execution_time_limit_exceeded.is_set()
        assert elapsed < 2.0
        assert len(ticks) >= 10
        with pytest.raises(docker.errors.NotFound):
            client.inspect_container(container['Id'])
    finally:
        try:
            client.remove_container(container['Id'], force=True)
        except docker.errors.NotFound:
            pass


@pytest.mark.skipif(not os.getenv('REAL_DOCKER'), reason='Real Docker court runs on GitHub')
def test_real_docker_success_and_name_reuse_survive_old_watchdog():
    import docker
    client = docker.APIClient(base_url='unix:///var/run/docker.sock', timeout=8)
    ns = load_subject(client)
    run = make_run(ns, 0.8)
    name = 'genesis-worker-court-name-reuse'
    first = client.create_container(os.environ['WORKER_TEST_IMAGE'],
                                    command=['sh', '-c', 'echo final-out; echo final-err >&2'],
                                    name=name, network_disabled=True)
    kind = ns['ProgramKind'].SCORING_PROGRAM
    asyncio.run(run._run_container_engine_cmd(first, kind))
    assert run.logs[kind]['returncode'] == 0
    assert b'final-out' in run.logs[kind]['stdout']['data']
    assert b'final-err' in run.logs[kind]['stderr']['data']
    assert not run._execution_time_limit_exceeded.is_set()
    successor = client.create_container(os.environ['WORKER_TEST_IMAGE'],
                                        command=['sh', '-c', 'sleep 3'], name=name, network_disabled=True)
    try:
        client.start(successor['Id'])
        time.sleep(0.95)
        assert client.inspect_container(successor['Id'])['State']['Running']
    finally:
        client.remove_container(successor['Id'], force=True)
