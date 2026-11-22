"""Load the portable graph implementation from this checkout, independent of sys.path."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

GRAPH_CONTRACT_PATH = Path(__file__).resolve().parents[1] / 'skills/figma-flow/scripts/graph.py'
_spec = spec_from_file_location('figma_flow_graph_contract', GRAPH_CONTRACT_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f'Cannot load graph contract from {GRAPH_CONTRACT_PATH}')
contract = module_from_spec(_spec)
_spec.loader.exec_module(contract)

decode_json = contract.decode_json


def read_json(path):
    return decode_json(Path(path).read_bytes())
