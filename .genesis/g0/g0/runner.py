from __future__ import annotations
from pathlib import Path
import json, subprocess, tempfile, os, sys, shutil, signal, math
from .bundle import Bundle

class RunError(RuntimeError): pass

def run_bundle(bundle: Bundle, request: dict, timeout_s=20, env_extra=None,
               max_output_bytes=1048576, memory_mb=512, cpu_s=10):
    """Bounded known-source execution, NOT an OS/network security sandbox.

    Same-UID ambient access remains possible. Resource bounds and a copied
    working directory do not justify executing arbitrary hostile source.
    """
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise RunError('invalid timeout')
    if max_output_bytes < 1 or memory_mb < 64 or cpu_s < 1:
        raise RunError('invalid resource bound')
    actual = Bundle.load(bundle.root)
    if (actual.bundle_id, actual.entrypoint, actual.kind) != (bundle.bundle_id, bundle.entrypoint, bundle.kind):
        raise RunError('bundle identity changed before execution')
    env={'PATH':os.environ.get('PATH',''),'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'}
    if env_extra: env.update(env_extra)
    def limits():
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb*1024*1024, memory_mb*1024*1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_output_bytes, max_output_bytes))
    with tempfile.TemporaryDirectory(prefix='g0-known-source-') as td:
        stage = Path(td)/'bundle'
        shutil.copytree(bundle.root, stage)
        if Bundle.load(stage).bundle_id != bundle.bundle_id:
            raise RunError('bundle identity changed while staging')
        entry = stage / bundle.entrypoint
        with (Path(td)/'stdout').open('w+b') as stdout, (Path(td)/'stderr').open('w+b') as stderr:
            p = subprocess.Popen([sys.executable, str(entry)], stdin=subprocess.PIPE,
                                 stdout=stdout, stderr=stderr, cwd=stage, env=env,
                                 start_new_session=(os.name == 'posix'),
                                 preexec_fn=limits if os.name == 'posix' else None)
            try:
                p.communicate(json.dumps(request, allow_nan=False).encode(), timeout=timeout_s)
            except subprocess.TimeoutExpired as exc:
                raise RunError('candidate timeout') from exc
            finally:
                if os.name == 'posix':
                    try:
                        os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif p.poll() is None:
                    p.kill()
                p.wait()
            stdout.seek(0); stderr.seek(0)
            out = stdout.read(max_output_bytes+1)
            err = stderr.read(max_output_bytes+1)
        if len(out) >= max_output_bytes or len(err) >= max_output_bytes:
            raise RunError('candidate output bound reached')
        if p.returncode != 0:
            raise RunError(f'rc={p.returncode} stderr={err[-4000:].decode(errors="replace")}')
        if Bundle.load(bundle.root).bundle_id != bundle.bundle_id:
            raise RunError('source identity changed during execution')
        try:
            obj=json.loads(out, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except Exception as exc:
            raise RunError('candidate output must be finite JSON') from exc
        if not isinstance(obj, dict):
            raise RunError('candidate output must be JSON object')
        return obj
