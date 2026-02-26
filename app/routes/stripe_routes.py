"""Stripe billing routes for Plant Pro Plan B2C SaaS."""

import json
import logging
import os

import stripe
from flask import Blueprint, jsonify, request

bp = Blueprint('stripe', __name__)
logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_uid() -> tuple:
    """Verify Firebase Bearer token and return (uid, None) or (None, error_response)."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None, (jsonify({'success': False, 'error': 'Missing Authorization header'}), 401)
    token = auth_header[len('Bearer '):]
    try:
        import firebase_admin.auth as fb_auth
        decoded = fb_auth.verify_id_token(token)
        return decoded['uid'], None
    except Exception as exc:
        logger.warning('Token verification failed: %s', exc)
        return None, (jsonify({'success': False, 'error': 'Invalid or expired token'}), 401)


def _users_col():
    """Return Firestore users collection."""
    from firebase_admin import firestore
    return firestore.client().collection('users')


def _stripe_key() -> str | None:
    return os.getenv('STRIPE_SECRET_KEY')


# ── POST /api/stripe/create-checkout-session ──────────────────────────────────

@bp.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    """Create a Stripe Checkout Session and return the redirect URL.

    Requires: Authorization: Bearer <firebase-id-token>
    """
    uid, err = _get_uid()
    if err:
        return err

    key = _stripe_key()
    if not key:
        return jsonify({'success': False, 'error': 'Stripe not configured (STRIPE_SECRET_KEY missing)'}), 500

    stripe.api_key = key

    # ── resolve or create Stripe customer ─────────────────────────────────────
    stripe_customer_id = None
    email = ''
    user_doc = _users_col().document(uid).get()
    if user_doc.exists:
        data = user_doc.to_dict() or {}
        stripe_customer_id = data.get('stripeCustomerId')
        email = data.get('email', '')

    if not stripe_customer_id:
        # Fetch email from Firebase Auth if not in users doc
        if not email:
            try:
                import firebase_admin.auth as fb_auth
                user_record = fb_auth.get_user(uid)
                email = user_record.email or ''
            except Exception:
                pass

        customer = stripe.Customer.create(
            email=email,
            metadata={'uid': uid},
        )
        stripe_customer_id = customer.id
        _users_col().document(uid).set(
            {'stripeCustomerId': stripe_customer_id, 'email': email},
            merge=True,
        )
        logger.info('Created Stripe customer %s for uid %s', stripe_customer_id, uid)

    # ── build checkout session ────────────────────────────────────────────────
    app_url = os.getenv('APP_URL', 'http://localhost:5010')
    

    session = stripe.checkout.Session.create(
        customer=stripe_customer_id,
        payment_method_types=['card'],
        mode='subscription',
        line_items=[{
            'price_data': {
                'currency': 'usd',
                # $0 free subscription — perfect for testing without any real charge.
                # Change to e.g. 50 ($0.50) or 999 ($9.99) for paid tiers.
                'unit_amount': 0,
                'recurring': {'interval': 'month'},
                'product_data': {
                    'name': 'Plant Pro Plan',
                    'description': 'Unlimited plant health checks + advanced AI analysis',
                },
            },
            'quantity': 1,
        }],
        metadata={'uid': uid},
        success_url=f'{app_url}/?subscription=success',
        cancel_url=f'{app_url}/?subscription=cancelled',
    )

    logger.info('Created checkout session %s for uid %s', session.id, uid)
    return jsonify({'success': True, 'checkout_url': session.url})


# ── GET /api/stripe/subscription-status ──────────────────────────────────────

@bp.route('/subscription-status', methods=['GET'])
def subscription_status():
    """Return the current user's plan, subscription status, and plant count.

    Requires: Authorization: Bearer <firebase-id-token>
    Response: { success, plan, subscriptionType, subscriptionStatus, numberOfPlants }
    """
    uid, err = _get_uid()
    if err:
        return err

    user_doc = _users_col().document(uid).get()
    if user_doc.exists:
        data = user_doc.to_dict() or {}
        plan = data.get('plan', 'free')
        return jsonify({
            'success': True,
            'plan': plan,
            'subscriptionType': data.get('subscriptionType', plan),
            'subscriptionStatus': data.get('subscriptionStatus', 'inactive'),
            'numberOfPlants': data.get('numberOfPlants', 0),
        })

    # First visit — initialise users/{uid} with free-tier defaults
    _users_col().document(uid).set({
        'plan': 'free',
        'subscriptionType': 'free',
        'subscriptionStatus': 'inactive',
        'numberOfPlants': 0,
    }, merge=True)
    return jsonify({
        'success': True,
        'plan': 'free',
        'subscriptionType': 'free',
        'subscriptionStatus': 'inactive',
        'numberOfPlants': 0,
    })


# ── POST /api/stripe/webhook ──────────────────────────────────────────────────

@bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhook events and update Firestore accordingly.

    Supported events:
      - checkout.session.completed        → upgrade user to pro
      - customer.subscription.deleted     → downgrade user to free
      - customer.subscription.paused      → mark subscription inactive
    """
    key = _stripe_key()
    if not key:
        return jsonify({'error': 'Stripe not configured'}), 500
    stripe.api_key = key

    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET', '')

    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            # Dev/local mode: skip signature verification (never use in production)
            logger.warning('STRIPE_WEBHOOK_SECRET not set — skipping signature verification')
            event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        logger.error('Webhook parse/signature error: %s', exc)
        return jsonify({'error': str(exc)}), 400

    event_type = event['type']
    logger.info('Stripe webhook received: %s', event_type)

    if event_type == 'checkout.session.completed':
        session_obj = event['data']['object']
        uid = (session_obj.get('metadata') or {}).get('uid')
        if uid:
            _users_col().document(uid).set({
                'plan': 'pro',
                'subscriptionType': 'pro',
                'subscriptionStatus': 'active',
                'stripeSubscriptionId': session_obj.get('subscription'),
            }, merge=True)
            logger.info('User %s upgraded to pro', uid)

    elif event_type in ('customer.subscription.deleted', 'customer.subscription.paused'):
        sub_obj = event['data']['object']
        customer_id = sub_obj.get('customer')
        if customer_id:
            # Locate user by Stripe customer ID
            docs = (
                _users_col()
                .where('stripeCustomerId', '==', customer_id)
                .limit(1)
                .stream()
            )
            for doc in docs:
                doc.reference.update({
                    'plan': 'free',
                    'subscriptionType': 'free',
                    'subscriptionStatus': 'inactive',
                })
                logger.info('User %s downgraded to free (%s)', doc.id, event_type)

    return jsonify({'success': True}), 200
