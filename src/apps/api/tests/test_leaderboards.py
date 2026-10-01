from django.urls import reverse
from rest_framework.test import APITestCase

import factories


class CompetitionLeaderboardStressTests(APITestCase):
    def setUp(self):
        self.creator = factories.UserFactory(username='creator', password='creator')
        self.other_user = factories.UserFactory(username='other_user', password='other')
        self.comp = factories.CompetitionFactory(created_by=self.creator)
        self.leaderboard = factories.LeaderboardFactory()
        self.phase = factories.PhaseFactory(competition=self.comp, leaderboard=self.leaderboard)
        factories.ColumnFactory(leaderboard=self.leaderboard, index=0)  # need to set index here otherwise it's seq

        for _ in range(10):
            factories.SubmissionFactory(phase=self.phase, leaderboard=self.leaderboard)

    def test_getting_many_submissions_doesnt_cause_too_many_queries(self):
        self.client.login(username='creator', password='creator')
        with self.assertNumQueries(11):
            resp = self.client.get(reverse('leaderboard-detail', args=(self.leaderboard.pk,)))
            assert resp.status_code == 200


class LeaderboardTest(APITestCase):
    def setUp(self):
        leaderboard1 = factories.LeaderboardFactory()
        leaderboard2 = factories.LeaderboardFactory()
        _ = factories.ColumnFactory(leaderboard=leaderboard1, index=0)
        _ = factories.ColumnFactory(leaderboard=leaderboard2, index=0)

    def test_get_all_leaderboards(self):
        url = reverse('leaderboard-list')
        resp = self.client.get(url)
        assert resp.status_code == 200
        assert resp.data == []


class HiddenLeaderboardTests(APITestCase):
    def setUp(self):
        self.admin = factories.UserFactory(username='admin', password='test', super_user=True)
        self.creator = factories.UserFactory(username='creator', password='test')
        self.collab = factories.UserFactory(username='collab', password='test')
        self.norm = factories.UserFactory(username='norm', password='test')
        self.comp = factories.CompetitionFactory(created_by=self.creator, collaborators=[self.collab])
        self.lb = factories.LeaderboardFactory(hidden=True)
        self.phase = factories.PhaseFactory(competition=self.comp, leaderboard=self.lb)
        factories.ColumnFactory(leaderboard=self.lb, index=0)

    def get_comp(self):
        return self.client.get(reverse('competition-detail', kwargs={'pk': self.comp.id}))

    def get_leaderboard(self):
        return self.client.get(reverse('leaderboard-detail', kwargs={'pk': self.lb.id}))

    def get_leaderboards(self, resp):
        data = resp.json()
        leaderboards = data.get('leaderboards', [])
        return leaderboards

    def test_creator_can_see_hidden_leaderboard_on_competition(self):
        self.client.force_login(self.creator)
        resp = self.get_comp()
        assert resp.status_code == 200
        leaderboards = self.get_leaderboards(resp)
        assert len(leaderboards) == 1
        assert leaderboards[0]['id'] == self.lb.id

    def test_admin_can_see_hidden_leaderboard_on_competition(self):
        self.client.force_login(self.admin)
        resp = self.get_comp()
        assert resp.status_code == 200
        leaderboards = self.get_leaderboards(resp)
        assert len(leaderboards) == 1
        assert leaderboards[0]['id'] == self.lb.id

    def test_collab_can_see_hidden_leaderboard_on_competition(self):
        self.client.force_login(self.collab)
        resp = self.get_comp()
        assert resp.status_code == 200
        leaderboards = self.get_leaderboards(resp)
        assert len(leaderboards) == 1
        assert leaderboards[0]['id'] == self.lb.id

    def test_normal_user_cannot_see_hidden_leaderboard_on_competition(self):
        self.client.force_login(self.norm)
        resp = self.get_comp()
        assert resp.status_code == 200
        leaderboards = self.get_leaderboards(resp)
        assert len(leaderboards) == 0

    def test_anonymous_user_cannot_see_hidden_leaderboard_on_competition(self):
        resp = self.get_comp()
        assert resp.status_code == 200
        leaderboards = self.get_leaderboards(resp)
        assert len(leaderboards) == 0

    def test_creator_can_see_leaderboard_entries(self):
        self.client.force_login(self.creator)
        resp = self.get_leaderboard()
        assert resp.status_code == 200
        assert 'submissions' in resp.json()

    def test_admin_can_see_leaderboard_entries(self):
        self.client.force_login(self.admin)
        resp = self.get_leaderboard()
        assert resp.status_code == 200
        assert 'submissions' in resp.json()

    def test_collab_can_see_leaderboard_entries(self):
        self.client.force_login(self.collab)
        resp = self.get_leaderboard()
        assert resp.status_code == 200
        assert 'submissions' in resp.json()

    def test_normal_user_cannot_see_leaderboard_entries(self):
        self.client.force_login(self.norm)
        resp = self.get_leaderboard()
        assert resp.status_code == 403
        assert 'You do not have permission' in resp.json().get('detail')

    def test_anonymous_user_cannot_see_leaderboard_entries(self):
        resp = self.get_leaderboard()
        assert resp.status_code == 403
        assert 'Authentication credentials were not provided.' in resp.json().get('detail')
        self.lb.hidden = False
        self.lb.save()
        resp = self.get_leaderboard()
        assert resp.status_code == 200


class LeaderboardNullScoreOrderingTests(APITestCase):
    def setUp(self):
        self.owner = factories.UserFactory(username='rank_owner', password='test')
        self.comp = factories.CompetitionFactory(created_by=self.owner)
        self.leaderboard = factories.LeaderboardFactory(primary_index=0)
        self.phase = factories.PhaseFactory(competition=self.comp, leaderboard=self.leaderboard)
        self.primary = factories.ColumnFactory(
            leaderboard=self.leaderboard,
            index=0,
            sorting='desc',
        )
        self.scored = factories.SubmissionFactory(
            phase=self.phase,
            owner=self.owner,
            leaderboard=self.leaderboard,
            status='Finished',
        )
        self.missing = factories.SubmissionFactory(
            phase=self.phase,
            owner=self.owner,
            leaderboard=self.leaderboard,
            status='Finished',
        )
        factories.SubmissionScoreFactory(
            column=self.primary,
            score=0.6,
            submissions=self.scored,
        )

    def test_missing_primary_score_is_ranked_after_scored_submission(self):
        resp = self.client.get(reverse('leaderboard-detail', args=(self.leaderboard.pk,)))

        assert resp.status_code == 200
        ids = [row['id'] for row in resp.data['submissions']]
        assert ids.index(self.scored.pk) < ids.index(self.missing.pk)

    def test_force_best_ignores_submission_missing_primary_score(self):
        from leaderboards.strategies import BestModeStrategy

        best = BestModeStrategy()._choose_best_submission(
            leaderboard=self.leaderboard,
            owner=self.owner,
            phase=self.phase,
        )

        assert best.pk == self.scored.pk

    def test_phase_serializer_puts_missing_primary_last(self):
        from api.serializers.leaderboards import LeaderboardPhaseSerializer

        rows = LeaderboardPhaseSerializer(self.phase).data['submissions']
        ids = [row['id'] for row in rows]
        assert ids.index(self.scored.pk) < ids.index(self.missing.pk)

    def test_ascending_primary_keeps_negative_score_ahead_of_missing(self):
        from api.serializers.leaderboards import LeaderboardEntriesSerializer, LeaderboardPhaseSerializer
        from leaderboards.strategies import BestModeStrategy

        self.primary.sorting = 'asc'
        self.primary.save()
        self.scored.scores.update(score=-0.2)
        for serializer, instance in (
            (LeaderboardEntriesSerializer, self.leaderboard),
            (LeaderboardPhaseSerializer, self.phase),
        ):
            ids = [row['id'] for row in serializer(instance).data['submissions']]
            assert ids.index(self.scored.pk) < ids.index(self.missing.pk)
        best = BestModeStrategy()._choose_best_submission(
            leaderboard=self.leaderboard, owner=self.owner, phase=self.phase,
        )
        assert best.pk == self.scored.pk

    def test_descending_secondary_breaks_primary_tie_with_missing_last(self):
        from leaderboards.strategies import BestModeStrategy

        factories.SubmissionScoreFactory(
            column=self.primary, score=0.6, submissions=self.missing,
        )
        secondary = factories.ColumnFactory(
            leaderboard=self.leaderboard, index=1, sorting='desc',
        )
        factories.SubmissionScoreFactory(
            column=secondary, score=-0.3, submissions=self.scored,
        )
        best = BestModeStrategy()._choose_best_submission(
            leaderboard=self.leaderboard, owner=self.owner, phase=self.phase,
        )
        assert best.pk == self.scored.pk

    def test_ascending_secondary_breaks_primary_tie_with_missing_last(self):
        from leaderboards.strategies import BestModeStrategy

        factories.SubmissionScoreFactory(
            column=self.primary, score=0.6, submissions=self.missing,
        )
        secondary = factories.ColumnFactory(
            leaderboard=self.leaderboard, index=1, sorting='asc',
        )
        factories.SubmissionScoreFactory(
            column=secondary, score=0.0, submissions=self.scored,
        )
        best = BestModeStrategy()._choose_best_submission(
            leaderboard=self.leaderboard, owner=self.owner, phase=self.phase,
        )
        assert best.pk == self.scored.pk
