"""Shared limits used by the native relay, Codex readers, and the published UI."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMITS_FILE = Path('library/figma-profile/read-limits.json')


def read_limits(root=ROOT):
    data = json.loads((root / LIMITS_FILE).read_bytes())
    if type(data.get('maxNodes')) is not int or data['maxNodes'] <= 0:
        raise ValueError('Read limits require a positive integer maxNodes')
    return data


def control_transport(policy):
    limits = policy['controlTransport']
    def positive(value):
        return type(value) is int and 0 < value <= 2**53-1
    for field in ('replyBytes','historyDetailReplyBytes','readinessReplyBytes','relayReplyBytes','changeReplyBytes'):
        if not positive(limits.get(field)):
            raise ValueError(f'Invalid control transport field: {field}')
    for field in ('normal','largeRead'):
        frame = limits[field]
        if (not positive(frame.get('bodyBytes')) or not positive(frame.get('readbackBytes'))
                or frame['bodyBytes'] < frame['readbackBytes']):
            raise ValueError(f'Invalid control transport envelope: {field}')
    if any(limits['normal'][key] >= limits['largeRead'][key] for key in ('bodyBytes','readbackBytes')):
        raise ValueError('Large signed reads require a larger envelope than ordinary traffic')
    return limits


ENDPOINT_TIMEOUTS = frozenset({'probe', 'request', 'bulkRequest', 'longPollSlack', 'metricsIngest',
                               'serverRead', 'serverLongPoll', 'serverMetricsIngest', 'localServerRead',
                               'pluginRequest'})
ENDPOINT_PORTS = frozenset({'control', 'draftReview', 'ownedWorkspace'})


def control_endpoint(policy):
    """Validate the loopback endpoint SSoT shared by Python tools and the plugin runtime."""
    import runtime_limits

    endpoint = policy['controlEndpoint']
    if set(endpoint) != {'bindHost', 'originHost', 'loopbackHosts', 'defaultPorts', 'timeoutsMs'}:
        raise ValueError('Control endpoint requires exactly bindHost, originHost, loopbackHosts, defaultPorts and timeoutsMs')
    hosts = endpoint['loopbackHosts']
    if (not isinstance(hosts, list) or len(set(hosts)) != len(hosts)
            or not all(isinstance(host, str) and host for host in hosts)
            or endpoint['bindHost'] not in hosts or endpoint['originHost'] not in hosts):
        raise ValueError('Control endpoint hosts must be unique loopback names that include bind and origin hosts')
    ports = endpoint['defaultPorts']
    if set(ports) != ENDPOINT_PORTS or not all(type(port) is int and port in runtime_limits.UNPRIVILEGED_PORTS
                                               for port in ports.values()):
        raise ValueError('Control endpoint default ports must be unprivileged TCP ports')
    timeouts = endpoint['timeoutsMs']
    if set(timeouts) != ENDPOINT_TIMEOUTS or not all(
            type(value) is int and 0 < value <= runtime_limits.NETWORK['maxControlPolicyTimeoutMs']
            for value in timeouts.values()):
        raise ValueError('Control endpoint timeouts must be positive millisecond integers')
    return endpoint

MAX_NODES = read_limits()['maxNodes']
