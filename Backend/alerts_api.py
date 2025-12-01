import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from supabase import create_client
import os
from auth import require_auth
from alert_engine import get_engine_status

logger = logging.getLogger(__name__)

alerts_bp = Blueprint('alerts', __name__, url_prefix='/api/alerts')


def get_supabase():
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    return create_client(url, key)


@alerts_bp.route('', methods=['GET'])
@require_auth
def list_alerts():
    try:
        status = request.args.get('status', 'active')
        severity = request.args.get('severity')
        limit = min(int(request.args.get('limit', 50)), 200)
        offset = int(request.args.get('offset', 0))

        supabase = get_supabase()

        query = supabase.table('alerts').select('*')

        if status != 'all':
            query = query.eq('status', status)

        if severity:
            query = query.eq('severity', severity)

        query = query.order('triggered_at', desc=True)

        query = query.range(offset, offset + limit - 1)

        response = query.execute()

        alerts = response.data if response.data else []

        logger.info(f"Fetched {len(alerts)} alerts for user {g.current_user.get('email')}")

        return jsonify({
            'alerts': alerts,
            'count': len(alerts),
            'offset': offset,
            'limit': limit
        }), 200

    except Exception as e:
        logger.error(f"Error fetching alerts: {str(e)}")
        return jsonify({'error': 'Failed to fetch alerts'}), 500


@alerts_bp.route('/<alert_id>', methods=['GET'])
@require_auth
def get_alert(alert_id):
    try:
        supabase = get_supabase()
        response = supabase.table('alerts').select('*').eq('id', alert_id).execute()

        if not response.data or len(response.data) == 0:
            return jsonify({'error': 'Alert not found'}), 404

        return jsonify(response.data[0]), 200

    except Exception as e:
        logger.error(f"Error fetching alert {alert_id}: {str(e)}")
        return jsonify({'error': 'Failed to fetch alert'}), 500


@alerts_bp.route('/<alert_id>/acknowledge', methods=['POST'])
@require_auth
def acknowledge_alert(alert_id):
    try:
        supabase = get_supabase()
        user_email = g.current_user.get('email')

        user_response = supabase.table('Users').select('id').eq('Email', user_email).execute()

        # Update alert status
        update_data = {
            'status': 'acknowledged',
            'acknowledged_at': datetime.now().isoformat()
        }

        if user_response.data and len(user_response.data) > 0:
            update_data['acknowledged_by'] = user_response.data[0]['id']
            logger.info(f"Alert {alert_id} acknowledged by {user_email} (user_id: {user_response.data[0]['id']})")
        else:
            logger.warning(f"User {user_email} not found in Users table - acknowledging alert without user tracking")

        response = supabase.table('alerts').update(update_data).eq('id', alert_id).execute()

        if not response.data or len(response.data) == 0:
            return jsonify({'error': 'Alert not found'}), 404

        return jsonify({
            'message': 'Alert acknowledged successfully',
            'alert': response.data[0]
        }), 200

    except Exception as e:
        logger.error(f"Error acknowledging alert {alert_id}: {str(e)}")
        return jsonify({'error': 'Failed to acknowledge alert'}), 500


@alerts_bp.route('/<alert_id>/resolve', methods=['POST'])
@require_auth
def resolve_alert(alert_id):
    try:
        supabase = get_supabase()

        # Update alert status
        update_data = {
            'status': 'resolved',
            'resolved_at': datetime.now().isoformat()
        }

        response = supabase.table('alerts').update(update_data).eq('id', alert_id).execute()

        if not response.data or len(response.data) == 0:
            return jsonify({'error': 'Alert not found'}), 404

        logger.info(f"Alert {alert_id} resolved by {g.current_user.get('email')}")

        return jsonify({
            'message': 'Alert resolved successfully',
            'alert': response.data[0]
        }), 200

    except Exception as e:
        logger.error(f"Error resolving alert {alert_id}: {str(e)}")
        return jsonify({'error': 'Failed to resolve alert'}), 500


@alerts_bp.route('/stats/summary', methods=['GET'])
@require_auth
def get_alert_stats():
    try:
        supabase = get_supabase()

        # Count active alerts by severity
        active_response = supabase.table('alerts').select('severity').eq('status', 'active').execute()
        active_alerts = active_response.data if active_response.data else []

        # Count acknowledged alerts
        ack_response = supabase.table('alerts').select('id').eq('status', 'acknowledged').execute()
        acknowledged_count = len(ack_response.data) if ack_response.data else 0

        # Count resolved alerts
        resolved_response = supabase.table('alerts').select('id').eq('status', 'resolved').execute()
        resolved_count = len(resolved_response.data) if resolved_response.data else 0

        # Count by severity
        severity_counts = {
            'low': 0,
            'medium': 0,
            'high': 0
        }

        for alert in active_alerts:
            severity = alert.get('severity', '').lower()
            if severity in severity_counts:
                severity_counts[severity] += 1

        stats = {
            'total_active': len(active_alerts),
            'total_acknowledged': acknowledged_count,
            'total_resolved': resolved_count,
            'by_severity': severity_counts,
            'engine_status': get_engine_status()
        }

        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Error fetching alert stats: {str(e)}")
        return jsonify({'error': 'Failed to fetch alert statistics'}), 500


@alerts_bp.route('/rules', methods=['GET'])
@require_auth
def list_alert_rules():
    try:
        supabase = get_supabase()
        response = supabase.table('alert_rules').select('*').order('category').order('severity', desc=True).execute()

        rules = response.data if response.data else []

        logger.info(f"Fetched {len(rules)} alert rules")

        return jsonify({
            'rules': rules,
            'count': len(rules)
        }), 200

    except Exception as e:
        logger.error(f"Error fetching alert rules: {str(e)}")
        return jsonify({'error': 'Failed to fetch alert rules'}), 500


@alerts_bp.route('/preferences', methods=['GET'])
@require_auth
def get_user_preferences():
    try:
        user_id = g.current_user.get('id')
        supabase = get_supabase()

        response = supabase.table('user_alert_preferences').select('*').eq('user_id', user_id).execute()

        preferences = response.data if response.data else []

        logger.info(f"Fetched {len(preferences)} alert preferences for user {g.current_user.get('email')}")

        return jsonify({
            'preferences': preferences,
            'count': len(preferences)
        }), 200

    except Exception as e:
        logger.error(f"Error fetching user preferences: {str(e)}")
        return jsonify({'error': 'Failed to fetch preferences'}), 500


@alerts_bp.route('/preferences/<rule_id>', methods=['PUT'])
@require_auth
def update_user_preference(rule_id):
    try:
        user_id = g.current_user.get('id')
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request body required'}), 400

        supabase = get_supabase()

        # Check if preference exists
        existing = supabase.table('user_alert_preferences').select('*').eq('user_id', user_id).eq('alert_rule_id', rule_id).execute()

        preference_data = {
            'user_id': user_id,
            'alert_rule_id': rule_id,
            'enabled': data.get('enabled', True),
            'notify_web': data.get('notify_web', True),
            'notify_email': data.get('notify_email', True)
        }

        # Add custom threshold if provided
        if 'custom_threshold_value' in data:
            preference_data['custom_threshold_value'] = data['custom_threshold_value']

        if existing.data and len(existing.data) > 0:
            # Update existing preference
            preference_data['updated_at'] = datetime.now().isoformat()
            response = supabase.table('user_alert_preferences').update(preference_data).eq('user_id', user_id).eq('alert_rule_id', rule_id).execute()
        else:
            # Insert new preference
            response = supabase.table('user_alert_preferences').insert(preference_data).execute()

        if not response.data or len(response.data) == 0:
            return jsonify({'error': 'Failed to save preference'}), 500

        logger.info(f"Updated alert preference for user {g.current_user.get('email')} on rule {rule_id}")

        return jsonify({
            'message': 'Preference updated successfully',
            'preference': response.data[0]
        }), 200

    except Exception as e:
        logger.error(f"Error updating user preference: {str(e)}")
        return jsonify({'error': 'Failed to update preference'}), 500


@alerts_bp.route('/engine/health', methods=['GET'])
@require_auth
def get_engine_health():
    try:
        status = get_engine_status()

        health = {
            'healthy': status.get('running', False),
            'status': status,
            'timestamp': datetime.now().isoformat()
        }

        return jsonify(health), 200

    except Exception as e:
        logger.error(f"Error checking engine health: {str(e)}")
        return jsonify({'error': 'Failed to check engine health'}), 500


# Error handlers for the blueprint
@alerts_bp.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Resource not found'}), 404


@alerts_bp.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500
