"""Administrator-managed site configuration stored in the database."""
from copy import deepcopy
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import SiteSetting, Plan
from .config import settings
from .vault import decrypt

GATEWAYS = {
    'razorpay': {'label': 'Razorpay', 'public': ['key_id'], 'secret': ['key_secret', 'webhook_secret'], 'required': ['key_id', 'key_secret']},
    'stripe': {'label': 'Stripe', 'public': ['publishable_key'], 'secret': ['secret_key', 'webhook_secret'], 'required': ['secret_key']},
    'ccavenue': {'label': 'CCAvenue', 'public': ['merchant_id', 'access_code'], 'secret': ['working_key'], 'required': ['merchant_id', 'access_code', 'working_key']},
}

DEFAULT_LANDING = {
    'brand': {'primary': 'Tura', 'accent': 'QRcode'},
    'hero': {
        'eyebrow': 'QR CODES · SHORT LINKS · BUSINESS CARDS',
        'title': 'Make every scan\na new possibility.',
        'subtitle': 'Create beautifully branded QR codes, share what matters, and turn everyday moments into meaningful connections.',
        'note': 'Sign in to create, save and manage your codes.',
        'signup_note': 'Create your workspace in about a minute',
        'panel_title': 'QR-8F3A91C4',
        'panel_badge': 'Editable · Active',
        'panel_rows': [
            {'label': 'Code created', 'value': 'Marketing team', 'accent': False},
            {'label': 'Logo and colors applied', 'value': 'Brand kit', 'accent': False},
            {'label': 'Exported for print', 'value': 'SVG · PDF', 'accent': False},
            {'label': 'First scan', 'value': 'Mobile · Mumbai', 'accent': False},
            {'label': 'Destination updated', 'value': 'No reprint needed', 'accent': True},
            {'label': 'Scans recorded', 'value': 'Device · referrer', 'accent': True},
        ],
    },
    'auth': {
        'heading': 'One scan. Endless possibilities.',
        'body': 'Bring your ideas, people, and places closer with codes and links you can update at any time.',
        'note': 'QR codes · short links · barcodes · business cards',
    },
    'sections': [
        {'id': 'features', 'type': 'cards', 'enabled': True, 'nav_label': 'What it does', 'heading': 'What it does', 'intro': '', 'body': '', 'note': '', 'button_label': '', 'items': [
            {'title': 'Your brand, in every detail', 'body': 'Choose your colors, find your pattern, and add a logo for a code that feels unmistakably yours.'},
            {'title': 'Printed once. Updated anytime.', 'body': 'Keep your printed codes relevant. Change an editable destination whenever your plans change.'},
            {'title': 'See your connections grow', 'body': 'Understand clicks and scans with clear activity trends, device insights, and useful reports.'},
            {'title': 'One organized workspace', 'body': 'Keep campaigns, short links, business cards, and bulk creations together and easy to find.'},
        ]},
        {'id': 'how-it-works', 'type': 'steps', 'enabled': True, 'nav_label': 'How it works', 'heading': 'How it works', 'intro': '', 'body': '', 'note': '', 'button_label': '', 'items': [
            {'title': 'Choose what to share', 'body': 'A website, contact details, a Wi-Fi network, or a message. Start with your content.'},
            {'title': 'Give it your signature', 'body': 'Make your code stand out with brand colors, a custom pattern, and your logo.'},
            {'title': 'Download. Share. Connect.', 'body': 'Export a high-resolution code for your screen, packaging, or next print run.'},
        ]},
        {'id': 'choose', 'type': 'list', 'enabled': True, 'nav_label': '', 'heading': 'Simple today. Flexible for tomorrow.', 'intro': 'Pick the right kind of code for the way you work.', 'body': '', 'note': '', 'button_label': '', 'items': [
            {'title': 'Static QR codes', 'body': 'Fixed content that stays in your QR code. Ideal for Wi-Fi details, contact information, and lasting links.'},
            {'title': 'Editable QR codes', 'body': 'Update your website destination and follow scan activity. Ideal for evolving content and campaigns.'},
        ]},
        {'id': 'pricing', 'type': 'pricing', 'enabled': True, 'nav_label': 'Pricing', 'heading': 'Plans', 'intro': 'Choose the plan that fits the way you work.', 'body': '', 'note': '', 'button_label': '', 'items': []},
        {'id': 'faq', 'type': 'faq', 'enabled': True, 'nav_label': 'FAQ', 'heading': 'Questions you might have', 'intro': '', 'body': '', 'note': '', 'button_label': '', 'items': [
            {'title': 'Do I need an account to create a QR code?', 'body': 'Yes. Sign in to create, download, save and manage your codes, use editable destinations, and view activity.'},
            {'title': 'What is the difference between static and editable QR codes?', 'body': 'A static QR code contains its content directly and cannot be updated after printing. An editable QR code uses a managed link, allowing you to change the destination and measure requests while your account and link remain active.'},
            {'title': 'Can I use my brand colors and logo?', 'body': 'Yes. Choose a dark QR color, a light background, a pattern, and an optional logo. Strong contrast helps keep your code easy to scan. Always test the final code before printing.'},
            {'title': 'Which download format should I choose?', 'body': 'PNG works well for everyday digital use. SVG scales cleanly for design work. PDF is a practical choice for print.'},
            {'title': 'How does activity tracking work?', 'body': 'Editable codes and short links record requests through their managed link. Repeat visits and automated previews can affect totals; static QR codes do not report scans.'},
        ]},
        {'id': 'cta', 'type': 'cta', 'enabled': True, 'nav_label': '', 'heading': 'Bring your ideas closer', 'intro': 'One workspace for every link, code, and connection.', 'body': '', 'note': '', 'button_label': 'Get started', 'items': []},
    ],
    'footer': {'tagline': 'QR codes · short links · barcodes · business cards'},
}


def get_setting(db: Session, key: str, default=None):
    row = db.get(SiteSetting, key)
    return deepcopy(row.value) if row else deepcopy(default)


def set_setting(db: Session, key: str, value: dict):
    row = db.get(SiteSetting, key)
    if row:
        row.value = value
    else:
        db.add(SiteSetting(key=key, value=value))


def saas_enabled(db: Session) -> bool:
    return bool(get_setting(db, 'saas', {}).get('enabled'))


def landing(db: Session) -> dict:
    content = get_setting(db, 'landing', DEFAULT_LANDING)
    # Saved content may predate the removal of the public generator.
    content['sections'] = [s for s in content['sections'] if s['type'] != 'generator']
    return content


def gateway_values(db: Session, name: str) -> dict:
    """Stored gateway configuration with its secrets decrypted, for server use only."""
    stored = get_setting(db, 'gateways', {}).get(name, {})
    meta = GATEWAYS[name]
    values = {'enabled': bool(stored.get('enabled')), 'mode': stored.get('mode', 'test')}
    for field in meta['public']:
        values[field] = stored.get(field, '')
    for field in meta['secret']:
        values[field] = decrypt(stored.get(field, ''))
    return values


def gateway_ready(db: Session, name: str) -> bool:
    values = gateway_values(db, name)
    return values['enabled'] and all(values[field] for field in GATEWAYS[name]['required'])


def available_gateways(db: Session) -> list[dict]:
    return [{'id': name, 'label': meta['label']} for name, meta in GATEWAYS.items() if gateway_ready(db, name)]


def plan_json(plan: Plan) -> dict:
    return {key: getattr(plan, key) for key in ('id', 'name', 'description', 'price_monthly', 'price_yearly', 'currency', 'max_codes', 'max_cards', 'max_projects', 'features', 'is_featured')}


def active_plans(db: Session) -> list[Plan]:
    return list(db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order, Plan.created_at)))


def public_site(db: Session) -> dict:
    enabled = saas_enabled(db)
    content = landing(db)
    sections = [s for s in content['sections'] if s['enabled'] and (enabled or s['type'] != 'pricing')]
    content['sections'] = sections
    if not enabled:
        content['hero']['signup_note'] = ''
    return {'saas_enabled': enabled, 'landing': content, 'plans': [plan_json(p) for p in active_plans(db)] if enabled else []}


def smtp_view(db: Session) -> dict:
    stored = get_setting(db, 'smtp', {})
    return {'host': stored.get('host', ''), 'port': stored.get('port', 587), 'username': stored.get('username', ''),
            'from_address': stored.get('from_address', ''), 'security': stored.get('security', 'starttls'),
            'has_password': bool(stored.get('password'))}


def smtp_config(db: Session) -> dict | None:
    """Administrator settings first, then the server environment."""
    stored = get_setting(db, 'smtp', {})
    if stored.get('host') and stored.get('from_address'):
        return {'host': stored['host'], 'port': stored.get('port', 587), 'username': stored.get('username', ''),
                'password': decrypt(stored.get('password', '')), 'from_address': stored['from_address'],
                'security': stored.get('security', 'starttls')}
    if settings.smtp_host and settings.smtp_from:
        return {'host': settings.smtp_host, 'port': settings.smtp_port, 'username': settings.smtp_user,
                'password': settings.smtp_password, 'from_address': settings.smtp_from,
                'security': 'starttls' if settings.smtp_starttls else 'none'}
    return None
