import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from supabase import create_client, Client
from dotenv import load_dotenv

from proxmox_client import get_proxmox
from influx_queries import (
    get_node_cpu_usage,
    get_node_memory_usage,
    get_node_storage_usage,
    execute_alert_query
)

load_dotenv()

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None

_cooldown_tracker: Dict[tuple, datetime] = {}


def get_supabase() -> Client:
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    return create_client(url, key)


def load_alert_rules() -> List[Dict[str, Any]]:
    try:
        supabase = get_supabase()
        response = supabase.table('alert_rules').select('*').eq('enabled', True).execute()

        rules = response.data if response.data else []
        logger.info(f"Loaded {len(rules)} enabled alert rules")
        return rules

    except Exception as e:
        logger.error(f"Error loading alert rules: {str(e)}")
        return []


def is_in_cooldown(rule_id: str, resource_id: str, cooldown_seconds: int) -> bool:
    key = (rule_id, resource_id)
    last_alert = _cooldown_tracker.get(key)

    if not last_alert:
        return False

    cooldown_end = last_alert + timedelta(seconds=cooldown_seconds)
    in_cooldown = datetime.now() < cooldown_end

    if in_cooldown:
        remaining = (cooldown_end - datetime.now()).seconds
        logger.debug(f"Alert {rule_id} for {resource_id} in cooldown ({remaining}s remaining)")

    return in_cooldown


def set_cooldown(rule_id: str, resource_id: str):
    key = (rule_id, resource_id)
    _cooldown_tracker[key] = datetime.now()
    logger.debug(f"Cooldown set for {rule_id} on {resource_id}")


def trigger_alert(
    rule: Dict[str, Any],
    resource_name: str,
    current_value: float,
    resource_type: str = 'node'
) -> Optional[str]:
    try:
        supabase = get_supabase()

        # Build alert title and message
        metric_display = rule['metric_type'].replace('_', ' ').title()
        title = f"{rule['severity'].upper()}: {metric_display} alert on {resource_name}"
        message = (
            f"{metric_display} is {current_value:.1f}%, "
            f"which exceeds the threshold of {rule['threshold_value']}%. "
            f"Please investigate the {resource_name} {resource_type}."
        )

        # Create alert record
        alert_data = {
            'alert_rule_id': rule['id'],
            'severity': rule['severity'],
            'category': rule['category'],
            'title': title,
            'message': message,
            'resource_type': resource_type,
            'resource_id': resource_name,  # For nodes, name is the ID
            'resource_name': resource_name,
            'node_name': resource_name,
            'metric_name': rule['metric_type'],
            'current_value': current_value,
            'threshold_value': rule['threshold_value'],
            'status': 'active',
            'triggered_at': datetime.now().isoformat(),
            'metadata': {
                'rule_name': rule['name'],
                'check_interval': rule['check_interval_seconds'],
                'triggered_by': 'alert_engine'
            }
        }

        response = supabase.table('alerts').insert(alert_data).execute()

        if not response.data or len(response.data) == 0:
            logger.error("Failed to create alert record")
            return None

        alert_id = response.data[0]['id']
        logger.info(f"Alert triggered: {title} (ID: {alert_id})")

        # Set cooldown
        set_cooldown(rule['id'], resource_name)

        # Send email for high-severity alerts
        if rule['severity'] == 'high':
            send_email_notification(response.data[0])

        return alert_id

    except Exception as e:
        logger.error(f"Error triggering alert: {str(e)}")
        return None


def send_email_notification(alert: Dict[str, Any]):
    try:
        supabase = get_supabase()

        users_response = supabase.table('Users').select('id, Email, Name').execute()

        if not users_response.data:
            logger.warning("No users found to send email notifications")
            return

        supabase_url = os.getenv('SUPABASE_URL')
        edge_function_url = f"{supabase_url}/functions/v1/send-alert-email"

        for user in users_response.data:
            if not user.get('Email'):
                continue

            try:
                # Call Edge Function for each user
                payload = {
                    'alert': alert,
                    'user': user
                }

                # Edge Functions require anon key for invocation
                response = requests.post(
                    edge_function_url,
                    json=payload,
                    headers={
                        'Authorization': f"Bearer {os.getenv('SUPABASE_SERVICE_ROLE_KEY')}",
                        'Content-Type': 'application/json'
                    },
                    timeout=10
                )

                if response.status_code == 200:
                    logger.info(f"Email sent to {user['Email']} for alert {alert['id']}")

                    supabase.table('alert_notifications').insert({
                        'alert_id': alert['id'],
                        'user_id': user['id'],
                        'notification_type': 'email',
                        'status': 'sent',
                        'email_address': user['Email'],
                        'sent_at': datetime.now().isoformat()
                    }).execute()

                else:
                    logger.error(f"Email failed for {user['Email']}: {response.text}")

                    supabase.table('alert_notifications').insert({
                        'alert_id': alert['id'],
                        'user_id': user['id'],
                        'notification_type': 'email',
                        'status': 'failed',
                        'email_address': user['Email'],
                        'email_error': response.text,
                        'sent_at': datetime.now().isoformat()
                    }).execute()

            except Exception as e:
                logger.error(f"Error sending email to {user.get('Email')}: {str(e)}")

    except Exception as e:
        logger.error(f"Error in email notification process: {str(e)}")


def evaluate_node_metric_rule(rule: Dict[str, Any]):
    try:
        proxmox = get_proxmox()
        nodes = proxmox.nodes.get()

        for node in nodes:
            node_name = node['node']

            current_value = None

            if rule['metric_type'] == 'cpu_usage':
                current_value = get_node_cpu_usage(node_name, time_range="5m")
            elif rule['metric_type'] == 'memory_usage':
                current_value = get_node_memory_usage(node_name, time_range="5m")
            elif rule['metric_type'] == 'storage_usage':
                current_value = get_node_storage_usage(node_name, storage_path="/", time_range="5m")
            else:
                # Fallback: use generic query execution
                params = {
                    'node_name': node_name,
                    'INFLUXDB_BUCKET': os.getenv('INFLUXDB_BUCKET', 'proxmox_metrics')
                }
                current_value = execute_alert_query(rule['influx_query'], params)

            if current_value is None:
                logger.debug(f"No data for {rule['name']} on node {node_name}")
                continue

            # Evaluate condition
            threshold = float(rule['threshold_value'])
            operator = rule['condition_operator']
            condition_met = False

            if operator == '>':
                condition_met = current_value > threshold
            elif operator == '>=':
                condition_met = current_value >= threshold
            elif operator == '<':
                condition_met = current_value < threshold
            elif operator == '<=':
                condition_met = current_value <= threshold
            elif operator == '==':
                condition_met = abs(current_value - threshold) < 0.01
            elif operator == '!=':
                condition_met = abs(current_value - threshold) >= 0.01

            if condition_met:
                logger.info(
                    f"Alert condition met: {rule['name']} on {node_name} "
                    f"(value: {current_value:.2f}, threshold: {threshold})"
                )

                # Check cooldown
                if not is_in_cooldown(rule['id'], node_name, rule['cooldown_seconds']):
                    trigger_alert(rule, node_name, current_value, resource_type='node')
                else:
                    logger.debug(f"Skipping alert (in cooldown): {rule['name']} on {node_name}")
            else:
                logger.debug(
                    f"Alert condition not met: {rule['name']} on {node_name} "
                    f"(value: {current_value:.2f}, threshold: {threshold})"
                )

                # Auto-resolve any active alerts for this rule + resource
                auto_resolve_alerts(rule['id'], node_name, current_value)

    except Exception as e:
        logger.error(f"Error evaluating rule {rule.get('name', 'unknown')}: {str(e)}")


def auto_resolve_alerts(rule_id: str, resource_name: str, current_value: float):
    try:
        supabase = get_supabase()

        response = supabase.table('alerts').select('*').eq('alert_rule_id', rule_id).eq('resource_id', resource_name).eq('status', 'active').execute()

        active_alerts = response.data if response.data else []

        if not active_alerts:
            return

        # Auto-resolve all active alerts
        for alert in active_alerts:
            update_data = {
                'status': 'auto_resolved',
                'resolved_at': datetime.now().isoformat(),
                'metadata': {
                    **alert.get('metadata', {}),
                    'auto_resolved': True,
                    'resolution_value': current_value,
                    'resolution_reason': 'Metric returned below threshold'
                }
            }

            supabase.table('alerts').update(update_data).eq('id', alert['id']).execute()

            logger.info(
                f"Auto-resolved alert {alert['id']} for {resource_name} "
                f"(current value: {current_value:.2f}, was: {alert.get('current_value', 'N/A')})"
            )

    except Exception as e:
        logger.error(f"Error auto-resolving alerts for {resource_name}: {str(e)}")


def schedule_alert_rules():
    global _scheduler

    if not _scheduler:
        logger.error("Scheduler not initialized")
        return

    _scheduler.remove_all_jobs()

    rules = load_alert_rules()

    for rule in rules:
        interval_seconds = rule.get('check_interval_seconds', 60)

        job_id = f"alert_rule_{rule['id']}"

        _scheduler.add_job(
            func=evaluate_node_metric_rule,
            trigger=IntervalTrigger(seconds=interval_seconds),
            args=[rule],
            id=job_id,
            name=rule['name'],
            replace_existing=True
        )

        logger.info(
            f"Scheduled alert rule: {rule['name']} "
            f"(every {interval_seconds}s, severity: {rule['severity']})"
        )

    logger.info(f"Scheduled {len(rules)} alert rules")


def start_alert_engine():
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.warning("Alert engine already running")
        return

    logger.info("Starting alert evaluation engine...")

    _scheduler = BackgroundScheduler()
    _scheduler.start()

    # Schedule alert rules
    schedule_alert_rules()

    _scheduler.add_job(
        func=schedule_alert_rules,
        trigger=IntervalTrigger(minutes=5),
        id='reload_rules',
        name='Reload Alert Rules',
        replace_existing=True
    )

    logger.info("Alert engine started successfully")


def stop_alert_engine():
    global _scheduler

    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Alert engine stopped")
    else:
        logger.warning("Alert engine not running")


def get_engine_status() -> Dict[str, Any]:
    global _scheduler

    if not _scheduler:
        return {
            'running': False,
            'jobs': 0,
            'cooldowns_active': 0
        }

    jobs = _scheduler.get_jobs()

    return {
        'running': _scheduler.running,
        'jobs': len(jobs),
        'cooldowns_active': len(_cooldown_tracker),
        'next_run_times': [
            {
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None
            }
            for job in jobs[:5]  # Show next 5 jobs
        ]
    }


if __name__ == "__main__":
    # Test the alert engine when run directly
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Starting alert engine in test mode...")
    print("Press Ctrl+C to stop\n")

    try:
        start_alert_engine()

        # Keep running
        import time
        while True:
            time.sleep(10)
            status = get_engine_status()
            print(f"\nEngine Status: {status}")

    except KeyboardInterrupt:
        print("\nStopping alert engine...")
        stop_alert_engine()
        print("Stopped.")
