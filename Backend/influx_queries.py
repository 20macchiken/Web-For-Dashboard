import os
import logging
from typing import Optional, Dict, Any
from influxdb_client import InfluxDBClient
from influxdb_client.client.query_api import QueryApi
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Singleton instance
_influxdb_client: Optional[InfluxDBClient] = None
_query_api: Optional[QueryApi] = None


def get_influxdb() -> InfluxDBClient:
    global _influxdb_client, _query_api

    if _influxdb_client is not None:
        return _influxdb_client

    # Get configuration from environment
    url = os.getenv('INFLUXDB_URL')
    token = os.getenv('INFLUXDB_TOKEN')
    org = os.getenv('INFLUXDB_ORG')

    if not all([url, token, org]):
        raise ValueError(
            "Missing required InfluxDB environment variables. "
            "Please set INFLUXDB_URL, INFLUXDB_TOKEN, and INFLUXDB_ORG in .env"
        )

    try:
        _influxdb_client = InfluxDBClient(
            url=url,
            token=token,
            org=org,
            timeout=30000  # 30 second timeout
        )
        _query_api = _influxdb_client.query_api()

        bucket = os.getenv('INFLUXDB_BUCKET', 'proxmox_metrics')
        test_query = f'from(bucket: "{bucket}") |> range(start: -1m) |> limit(n: 1)'
        _query_api.query(test_query)

        logger.info(f"Successfully connected to InfluxDB at {url}")
        return _influxdb_client

    except Exception as e:
        logger.error(f"Failed to connect to InfluxDB: {str(e)}")
        _influxdb_client = None
        _query_api = None
        raise


def get_query_api() -> QueryApi:
    global _query_api
    if _query_api is None:
        get_influxdb()
    return _query_api


def close_influxdb():
    global _influxdb_client, _query_api
    if _influxdb_client:
        _influxdb_client.close()
        _influxdb_client = None
        _query_api = None
        logger.info("InfluxDB connection closed")


def get_node_cpu_usage(node_name: str, time_range: str = "5m") -> Optional[float]:
    try:
        bucket = os.getenv('INFLUXDB_BUCKET', 'proxmox_metrics')
        # cpustat measurement returns CPU as a fraction (0.004 = 0.4%), so multiply by 100
        query = f'''
from(bucket: "{bucket}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "cpustat")
  |> filter(fn: (r) => r._field == "cpu")
  |> filter(fn: (r) => r.host == "{node_name}")
  |> mean()
  |> map(fn: (r) => ({{ r with _value: r._value * 100.0 }}))
'''

        query_api = get_query_api()
        result = query_api.query(query)

        if not result or len(result) == 0:
            logger.warning(f"No CPU data found for node {node_name}")
            return None

        # Extract value from result
        for table in result:
            for record in table.records:
                cpu_value = record.get_value()
                logger.debug(f"Node {node_name} CPU: {cpu_value:.2f}%")
                return float(cpu_value)

        return None

    except Exception as e:
        logger.error(f"Error querying node CPU usage for {node_name}: {str(e)}")
        return None


def get_node_memory_usage(node_name: str, time_range: str = "5m") -> Optional[float]:
    try:
        bucket = os.getenv('INFLUXDB_BUCKET', 'proxmox_metrics')
        # Calculate percentage from memused and memtotal
        query = f'''
memUsed = from(bucket: "{bucket}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "memory")
  |> filter(fn: (r) => r._field == "memused")
  |> filter(fn: (r) => r.host == "{node_name}")
  |> mean()

memTotal = from(bucket: "{bucket}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "memory")
  |> filter(fn: (r) => r._field == "memtotal")
  |> filter(fn: (r) => r.host == "{node_name}")
  |> mean()

join(tables: {{used: memUsed, total: memTotal}}, on: ["host"])
  |> map(fn: (r) => ({{
      _value: r._value_used / r._value_total * 100.0,
      _time: r._time,
      host: r.host
    }}))
'''

        query_api = get_query_api()
        result = query_api.query(query)

        if not result or len(result) == 0:
            logger.warning(f"No memory data found for node {node_name}")
            return None

        # Extract value from result
        for table in result:
            for record in table.records:
                mem_value = record.get_value()
                logger.debug(f"Node {node_name} Memory: {mem_value:.2f}%")
                return float(mem_value)

        return None

    except Exception as e:
        logger.error(f"Error querying node memory usage for {node_name}: {str(e)}")
        return None


def get_node_storage_usage(
    node_name: str,
    storage_path: str = "/",
    time_range: str = "5m"
) -> Optional[float]:
    try:
        bucket = os.getenv('INFLUXDB_BUCKET', 'proxmox_metrics')
        # Note: blockstat may not have path tag, so only filter by path if it's explicitly set
        path_filter = f'|> filter(fn: (r) => r.path == "{storage_path}")' if storage_path and storage_path != "/" else ''

        query = f'''
from(bucket: "{bucket}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "blockstat")
  |> filter(fn: (r) => r._field == "per")
  |> filter(fn: (r) => r.host == "{node_name}")
  {path_filter}
  |> mean()
'''

        query_api = get_query_api()
        result = query_api.query(query)

        if not result or len(result) == 0:
            logger.warning(f"No storage data found for node {node_name} path {storage_path}")
            return None

        # Extract value from result
        for table in result:
            for record in table.records:
                storage_value = record.get_value()
                logger.debug(f"Node {node_name} Storage ({storage_path}): {storage_value:.2f}%")
                return float(storage_value)

        return None

    except Exception as e:
        logger.error(f"Error querying node storage usage for {node_name}: {str(e)}")
        return None


def execute_alert_query(query_template: str, params: Dict[str, Any]) -> Optional[float]:
    try:
        # Substitute parameters in query template
        query = query_template
        for key, value in params.items():
            query = query.replace(f"${{{key}}}", str(value))

        query_api = get_query_api()
        result = query_api.query(query)

        if not result or len(result) == 0:
            logger.debug(f"No data returned from alert query")
            return None

        # Extract first value from result
        for table in result:
            for record in table.records:
                value = record.get_value()
                logger.debug(f"Alert query result: {value}")
                return float(value)

        return None

    except Exception as e:
        logger.error(f"Error executing alert query: {str(e)}")
        logger.debug(f"Query: {query}")
        return None


# Utility function for testing
def test_connection() -> bool:
    try:
        client = get_influxdb()
        bucket = os.getenv('INFLUXDB_BUCKET', 'proxmox_metrics')

        # Try a simple query
        query = f'from(bucket: "{bucket}") |> range(start: -5m) |> limit(n: 5)'
        query_api = get_query_api()
        result = query_api.query(query)

        logger.info("InfluxDB connection test successful")
        logger.info(f"Query returned {len(result)} tables")
        return True

    except Exception as e:
        logger.error(f"InfluxDB connection test failed: {str(e)}")
        return False


def get_historical_metrics(start_time: str, end_time: str) -> Dict[str, list]:
    try:
        bucket = os.getenv('INFLUXDB_BUCKET', 'proxmox_metrics')
        query_api = get_query_api()

        results = {
            'cpu': [],
            'memory': [],
            'storage': []
        }

        # Query CPU metrics
        cpu_query = f'''
from(bucket: "{bucket}")
  |> range(start: {start_time}, stop: {end_time})
  |> filter(fn: (r) => r._measurement == "cpustat")
  |> filter(fn: (r) => r._field == "cpu")
  |> map(fn: (r) => ({{ r with _value: r._value * 100.0 }}))
'''

        cpu_result = query_api.query(cpu_query)
        for table in cpu_result:
            for record in table.records:
                results['cpu'].append({
                    'time': record.get_time().isoformat() if record.get_time() else None,
                    'host': record.values.get('host', 'unknown'),
                    'value': float(record.get_value()) if record.get_value() is not None else 0.0
                })

        # Query Memory metrics
        mem_query = f'''
memUsed = from(bucket: "{bucket}")
  |> range(start: {start_time}, stop: {end_time})
  |> filter(fn: (r) => r._measurement == "memory")
  |> filter(fn: (r) => r._field == "memused")

memTotal = from(bucket: "{bucket}")
  |> range(start: {start_time}, stop: {end_time})
  |> filter(fn: (r) => r._measurement == "memory")
  |> filter(fn: (r) => r._field == "memtotal")

join(tables: {{used: memUsed, total: memTotal}}, on: ["host", "_time"])
  |> map(fn: (r) => ({{
      _time: r._time,
      _value: r._value_used / r._value_total * 100.0,
      host: r.host
    }}))
'''

        mem_result = query_api.query(mem_query)
        for table in mem_result:
            for record in table.records:
                results['memory'].append({
                    'time': record.get_time().isoformat() if record.get_time() else None,
                    'host': record.values.get('host', 'unknown'),
                    'value': float(record.get_value()) if record.get_value() is not None else 0.0
                })

        # Query Storage metrics
        storage_query = f'''
from(bucket: "{bucket}")
  |> range(start: {start_time}, stop: {end_time})
  |> filter(fn: (r) => r._measurement == "blockstat")
  |> filter(fn: (r) => r._field == "per")
'''

        storage_result = query_api.query(storage_query)
        for table in storage_result:
            for record in table.records:
                results['storage'].append({
                    'time': record.get_time().isoformat() if record.get_time() else None,
                    'host': record.values.get('host', 'unknown'),
                    'path': record.values.get('path', '/'),
                    'value': float(record.get_value()) if record.get_value() is not None else 0.0
                })

        logger.info(f"Retrieved {len(results['cpu'])} CPU, {len(results['memory'])} memory, {len(results['storage'])} storage metrics")
        return results

    except Exception as e:
        logger.error(f"Error querying historical metrics: {str(e)}")
        return {'cpu': [], 'memory': [], 'storage': []}


if __name__ == "__main__":
    # Test the connection when run directly
    logging.basicConfig(level=logging.DEBUG)

    print("Testing InfluxDB connection...")
    if test_connection():
        print("\nConnection successful!\n")

        # Test node metric queries
        print("Testing node metric queries (using 'pve' as example node)...")
        print("Note: Replace 'pve' with your actual Proxmox node name\n")

        cpu = get_node_cpu_usage('pve')
        print(f"Node CPU: {cpu}%" if cpu else "No CPU data found")

        mem = get_node_memory_usage('pve')
        print(f"Node Memory: {mem}%" if mem else "No memory data found")

        storage = get_node_storage_usage('pve')
        print(f"Node Storage: {storage}%" if storage else "No storage data found")
    else:
        print("\nConnection failed. Check your .env configuration.")
