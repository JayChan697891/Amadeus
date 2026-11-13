"""Observe the completed live flow, accept only the reviewed document, then reopen."""
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

BASE = Path('/root/amadeus-continuous-monotonic-live-20261113')
sys.path.insert(0, str(BASE))
import pilot
from credential_home import mounts
from agentsync.proposals import parse_proposal
from agentsync.relay_queue import RelayQueue
from agentsync.verified_proposal_flow import VerifiedProposalFlow


def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def inspect(final=False):
    members = pilot.runtime()
    cleanup = pilot.load('auth-cleanup.json')
    assert all(cleanup[key] is True for key in (
        'temporary_auth_absent', 'home_unmounted', 'private_home_empty'))
    assert not mounts() and not any(pilot.HOME.iterdir())
    core, runner = pilot.core_and_relay()
    state = pilot.load('state.json')
    pilot.pinned(core, state)
    result, dispatch = pilot.load('result.json'), pilot.load('dispatch-observation.json')
    assert result['real_model_calls'] == 2 and dispatch['error_code'] is None
    assert result['outcome'] == dispatch['outcome']
    assert result['outcome']['state'] == 'handoff' and result['outcome']['handoff']['state'] == 'resolved'
    assert result['verification'] == 'unverified'
    receiver = pilot.load('receiver-state.json')
    tasks, authors, contexts, attempts_by_actor = {}, {}, {}, {}
    for who, task_id in (('producer', state['task']['id']), ('receiver', receiver['task_id'])):
        recorded = dispatch['actors'][who]
        assert recorded['captured_start_invoked'] is True and recorded['exact_authorizations'] == 1
        assert pilot.load('auth-route-' + who + '.json')['recognized_chatgpt_route'] is True
        attempts = runner.owner_inspect_attempts(state['owner']['project_id'], task_id,
            admin_token=state['owner']['admin_token'])
        attempts_by_actor[who] = [pilot.attempt_summary(a) for a in attempts]
        assert attempts_by_actor[who] == recorded['attempts']
        first, second = attempts
        assert first.parent_ended is True and first.exit_code == 0
        assert first.status == 'proposal_received' and second.state == 'not_dispatched'
        assert first.admission is not None and first.admission.state == 'both_reservations_recorded'
        expected_plan = (state['plan_sha256'] if who == 'producer'
            else pilot.load('receiver-request.json')['decision_sha256'])
        assert first.admission.plan_sha256 == expected_plan
        assert first.agent_sha256 == pilot.digest(state[who]['agent_id'])
        actor = pilot.actor_for(state, who, workspace=None if who == 'producer' else receiver)
        stored = runner.observe_codex_proposal(actor, task_id)
        assert stored.state == 'proposal_stored' and stored.context_version == 1
        context = core.execute('get_context', {**pilot.auth(state, who),
            'context_id': stored.context_id, 'version': stored.context_version})
        assert text_sha(context['content']) == stored.content_sha256
        assert context['author_agent_id'] == state[who]['agent_id']
        authors[who] = context['author_agent_id']
        contexts[who] = (stored, context)
        tasks[who] = pilot.task(core, state, task_id)
    assert len({authors['producer'], authors['receiver'], state['reviewer']['agent_id']}) == 3
    assert pilot.task_summary(tasks['producer']) == result['producer_task']
    assert tasks['producer']['status'] == 'completed' and tasks['producer']['task_verification'] == 'verified'
    assert tasks['receiver']['dependencies'] == [tasks['producer']['id']]
    assert tasks['receiver']['task_verification'] == 'unverified'
    assert tasks['receiver']['status'] == ('completed' if final else 'review')
    stored, context = contexts['receiver']
    assert stored.context_id == result['review']['context_id']
    assert stored.content_sha256 == result['review']['content_sha256']
    value = json.loads(context['content'])
    assert value['task_id'] == receiver['task_id'] and value['execution_provenance'] == 'unverified'
    note = parse_proposal(json.dumps({'files': value['files']}), ['review.md'])[0]['content']
    heading, separator, reasons = note.strip().partition('\n')
    assert separator and heading in ('Verdict: PASS', 'Verdict: NEEDS_CHANGES')
    assert reasons.lstrip().startswith('Reasons:') and reasons.lstrip().removeprefix('Reasons:').strip()
    if final:
        accepted = pilot.load('host-acceptance.json')
        assert accepted['review_note_sha256'] == text_sha(note)
        assert accepted['review_task'] == pilot.task_summary(tasks['receiver'])
        assert tasks['receiver']['latest_review']['reviewer_agent_id'] == state['reviewer']['agent_id']
        assert tasks['receiver']['latest_review']['accept'] is True
    else:
        assert pilot.task_summary(tasks['receiver']) == result['receiver_task']
    execution = pilot.load('execution.json')['execution']['result']
    assert execution['expected_case_count'] == execution['passed_case_count'] == 8
    assert execution['source_sha256'] == pilot.sha(BASE / 'source-for-review.py.txt')
    assert execution['cleanup_confirmed'] is True
    assert len(execution['isolation']['checks']) == 19 and all(execution['isolation']['checks'].values())
    container_id = execution['container_id']
    assert re.fullmatch('[0-9a-f]{64}', container_id)
    check = subprocess.run(['/usr/bin/docker', 'container', 'inspect', container_id],
        capture_output=True, text=True, timeout=10)
    assert check.returncode == 1 and json.loads(check.stdout) == []
    assert 'No such container:' in check.stderr or 'No such object:' in check.stderr
    assert RelayQueue(runner).owner_observe_pending(state['owner']['project_id'],
        admin_token=state['owner']['admin_token']) is None
    record = {'timestamp': pilot.timestamp(), 'product_sha': pilot.PRODUCT,
        'producer_task': pilot.task_summary(tasks['producer']), 'review_task': pilot.task_summary(tasks['receiver']),
        'different_core_model_authors': True, 'host_reviewer_distinct_from_both': True,
        'review_context_sha256': stored.content_sha256, 'review_note_sha256': text_sha(note),
        'review_note_utf8_bytes': len(note.encode()), 'review_verdict': heading.removeprefix('Verdict: '),
        'auth_cleanup_confirmed': True, 'source_and_worktrees_unchanged': True,
        'container_absent': True, 'queue_pending': False, 'host_document_acceptance': final,
        'attempts': attempts_by_actor, **members}
    return core, runner, state, receiver, record, note


def main():
    os.umask(0o077)
    args = sys.argv[1:]
    if args == ['submitted']:
        *_, record, note = inspect()
        with (BASE / 'private-review.md').open('x', encoding='utf-8') as out:
            out.write(note)
        pilot.save('review-observation.json', record)
        print(json.dumps({'observed': True, 'note_sha256': record['review_note_sha256']}))
    elif len(args) == 4 and args[0] == 'review-once' and args[-1] == '--document-reviewed':
        core, _, state, receiver, record, _ = inspect()
        assert all(re.fullmatch('[0-9a-f]{64}', a) for a in args[1:3])
        assert args[1:3] == [record['review_context_sha256'], record['review_note_sha256']]
        assert pilot.load('review-observation.json')['review_note_sha256'] == args[2]
        assert pilot.sha(BASE / 'private-review.md') == args[2]
        pilot.save('host-review-entry.json', {'timestamp': pilot.timestamp(), 'note_sha256': args[2]})
        accepted = core.execute('review_task', {**pilot.auth(state, 'reviewer'), 'task_id': receiver['task_id'],
            'expected_version': record['review_task']['version'], 'accept': True,
            'evidence': 'Host acceptance of source-only model review document SHA256 ' + args[2],
            'request_id': pilot.REQUEST + '-document-acceptance'})
        assert accepted['status'] == 'completed' and accepted['task_verification'] == 'unverified'
        pilot.save('host-acceptance.json', {'timestamp': pilot.timestamp(), 'review_task': pilot.task_summary(accepted),
            'review_context_sha256': args[1], 'review_note_sha256': args[2], 'verification': 'unverified'})
        print('Host accepted the review document; verification remains unverified.')
    elif args == ['reopen']:
        core, runner, state, receiver, record, _ = inspect(final=True)
        before = core.execute('list_tasks', pilot.auth(state))
        queue = RelayQueue(runner)
        history = asdict(queue.owner_history(state['owner']['project_id'], admin_token=state['owner']['admin_token']))
        calls = []
        async def forbidden(review):
            calls.append(review.plan_sha256)
            raise AssertionError('A resolved handoff must not request another launch')
        def build(who, workspace):
            assert who == pilot.handoff_request(state).receiver
            assert workspace.task_id == receiver['task_id'] and workspace.worktree_id == receiver['worktree_id']
            return pilot.actor_for(state, 'receiver', forbidden, receiver)
        outcome = asyncio.run(VerifiedProposalFlow(core, BASE, BASE / 'receipts').resume_receiver(
            pilot.handoff_request(state), admin_token=state['owner']['admin_token'], build_receiver=build))
        assert json.loads(json.dumps(asdict(outcome))) == pilot.load('result.json')['outcome']['handoff']
        assert calls == [] and before == core.execute('list_tasks', pilot.auth(state))
        assert history == asdict(queue.owner_history(state['owner']['project_id'], admin_token=state['owner']['admin_token']))
        *_, after, _ = inspect(final=True)
        assert record['attempts'] == after['attempts']
        pilot.save('final-observation.json', {**after, 'reopen_authority_calls': 0,
            'reopen_tasks_attempts_history_unchanged': True, 'model_calls_on_reopen': 0})
        print('Reopened completed flow: same outcome, no new authority, attempts or tasks.')
    else:
        raise SystemExit('Use submitted, review-once CONTEXT_SHA NOTE_SHA --document-reviewed, or reopen.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error_code': pilot.error_code(exc)}))
        raise SystemExit(1) from None
