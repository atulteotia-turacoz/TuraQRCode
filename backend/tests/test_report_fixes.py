from sqlalchemy import text
from app.db import engine
from app.qr import payload


def test_short_alias_gets_a_readable_message(client, member):
    r = client.post('/api/codes', json={'name': 'Alias', 'content': {'url': 'https://example.com'}, 'alias': 'ab'})
    assert r.status_code == 422
    assert 'String should' not in r.json()['detail'] and 'custom alias' in r.json()['detail']


def test_generic_length_errors_name_the_field(client, member):
    r = client.post('/api/codes', json={'name': '', 'content': {'url': 'https://example.com'}})
    assert r.status_code == 422 and r.json()['detail'] == 'The name needs at least 1 characters.'


def test_bulk_rows_explain_the_real_problem(client, member):
    rows = [{'name': 'Good', 'content': {'url': 'https://example.com'}}, {'name': 'Bad url', 'content': {'url': 'www.turacoz'}}, {'name': 'Bad alias', 'content': {'url': 'https://example.com'}, 'alias': 'x'}]
    results = client.post('/api/codes/bulk', json={'rows': rows}).json()['results']
    assert results[0]['success']
    assert 'Check the name, content' not in results[1]['error'] and 'http' in results[1]['error']
    assert 'custom alias' in results[2]['error']


def test_bulk_rows_can_target_a_project(client, member):
    project = client.post('/api/projects', json={'name': 'Campaign batch'}).json()
    created = client.post('/api/codes/bulk', json={'rows': [{'name': 'In project', 'content': {'url': 'https://example.com'}, 'project_id': project['id']}]}).json()
    assert created['results'][0]['code']['project_id'] == project['id']


def test_owner_pause_and_activate_are_logged(client, member, code):
    assert client.patch('/api/codes/' + code['id'], json={'is_active': False}).status_code == 200
    assert client.patch('/api/codes/' + code['id'], json={'is_active': False}).status_code == 200
    assert client.patch('/api/codes/' + code['id'], json={'is_active': True}).status_code == 200
    with engine().connect() as c:
        actions = c.execute(text("SELECT action FROM audit_log WHERE actor_id=:u AND action LIKE 'code.%' ORDER BY created_at"), {'u': member['id']}).scalars().all()
    assert actions == ['code.paused', 'code.activated']


def test_phone_links_drop_spaces():
    assert payload('phone', {'phone': '+91 98765 43210'}) == 'tel:+919876543210'


def test_unavailable_page_uses_the_app_palette(client):
    page = client.get('/r/does-not-exist-anywhere')
    assert page.status_code == 404 and '#9E2B25' in page.text and '#2563eb' not in page.text
