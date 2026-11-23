"""Index historical release witnesses as development candidates without executing them."""
from collections import defaultdict
from collections.abc import Mapping
from hashlib import sha256
import re
import subprocess

from graph_document import decode_json
from release_ownership import pointer_parts, relative


REVIEW_PREFIX = 'release/reviews/'
REVIEW_SCHEMA = 'figma-flow-major-review-v1'
WITNESS_SCHEMAS = {None, 'figma-flow-major-witness-v1', 'figma-flow-major-review-witness-v1'}
INPUT_ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError, subprocess.SubprocessError)


def digest_value(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Expected a lowercase SHA-256 digest.')
    return value


def nonempty_list(value):
    if not isinstance(value, list) or not value:
        raise ValueError('Expected a nonempty array.')
    return value


def nonempty_text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Expected nonempty text.')
    return value


def review_path(surface):
    if not isinstance(surface, str) or not re.fullmatch(r'[a-z][a-z0-9-]*', surface):
        raise ValueError(f'Invalid release surface ID: {surface!r}')
    return f'{REVIEW_PREFIX}{surface}.json'


def _result(checks, reasons):
    if reasons:
        return {'status': 'needs-review', 'reason': ' '.join(sorted(set(reasons))), 'checks': checks}
    return {'status': 'historical-candidates' if checks else 'no-file-witness', 'checks': checks}


class WitnessIndex:
    def __init__(self, read, paths, surfaces):
        self._read = read
        self._paths = frozenset(paths)
        self._documents = {}
        self._invalid_documents = {}
        self.inputs = {}
        self._checks = defaultdict(list)
        self._path_errors = defaultdict(list)
        self._surface_errors = defaultdict(list)
        self._reverse = defaultdict(list)
        review_surfaces = (
            [key for key, spec in surfaces.items() if spec['coverage'] == 'review']
            if isinstance(surfaces, Mapping) else surfaces
        )
        for surface in sorted(set(review_surfaces)):
            self._index_review(surface)

    def _digest(self, path):
        if path not in self._paths:
            raise FileNotFoundError(f'Historical evidence is absent: {path}')
        if path not in self.inputs:
            self.inputs[path] = sha256(self._read(path)).hexdigest()
        return self.inputs[path]

    def _document(self, path):
        if path in self._invalid_documents:
            raise ValueError(self._invalid_documents[path])
        if path not in self._documents:
            if path not in self._paths:
                raise FileNotFoundError(f'Historical evidence is absent: {path}')
            raw = self._read(path)
            stamp = sha256(raw).hexdigest()
            self.inputs[path] = stamp
            try:
                self._documents[path] = decode_json(raw)
            except ValueError as error:
                self._invalid_documents[path] = str(error)
                raise
        return self._documents[path]

    def _add_route(self, trigger, surface, review, covered, *, witness=None, reason=None, check=None):
        route = {'surface': surface, 'review': review, 'coveredPaths': sorted(covered),
                 'status': 'needs-review' if reason else 'historical-candidates'}
        if witness is not None:
            route['witness'] = witness
        if reason:
            route['reason'] = reason
        if check is not None:
            route.update(test=check['test'], case=check['case'])
        if route not in self._reverse[trigger]:
            self._reverse[trigger].append(route)

    def _test_status(self, test, case, expected):
        present = test in self._paths
        try:
            actual = self._digest(test) if present else None
        except INPUT_ERRORS:
            return 'unreadable-source', None, f'Cannot read the historical test for {case}: {test}.'
        if not present:
            return 'missing-source', None, f'Historical test is missing for {case}: {test}.'
        if actual != expected:
            return 'stale-source', actual, f'Historical test bytes changed for {case}: {test}.'
        return 'historical-match', actual, None

    def _witness_checks(self, witness, fingerprint, stamp, authority, covered):
        proof = self._document(witness)
        if self.inputs[witness] != stamp:
            raise ValueError(f'Mapped witness file differs from its declaration: {witness}')
        if (not isinstance(proof, dict) or proof.get('schema') not in WITNESS_SCHEMAS or proof['surfaceFingerprint'] != fingerprint
                or proof['status'] != 'passed'):
            raise ValueError(f'Mapped witness is incomplete or bound to another review: {witness}')
        items = []
        witnessed = set()
        for check in nonempty_list(proof['checks']):
            if check['authority'] != authority:
                raise ValueError(f'Mapped witness names a different authority: {witness}')
            nonempty_text(check['assertion'])
            if 'observed' not in check:
                raise ValueError(f'Mapped witness omits the observation: {witness}')
            paths = set(map(relative, nonempty_list(check['covers']))) & covered
            witnessed.update(paths)
            test = relative(check['test'])
            case = nonempty_text(check['case'])
            expected = digest_value(check['testSha256'])
            items.append((test, case, expected, paths))
        if witnessed != covered:
            raise ValueError(f'Mapped witness does not account for all bound source files: {witness}')
        return items

    def _index_review(self, surface):
        document = review_path(surface)
        if document not in self._paths:
            self._add_route(document, surface, document, (), reason=f'Historical review is absent: {document}.')
            return
        covered = set()
        errors = []
        try:
            review = self._document(document)
            if (review['schema'] != REVIEW_SCHEMA or review['surface'] != surface
                    or review.get('openFindings') != [] or review.get('status') not in (None, 'complete')):
                raise ValueError(f'Unexpected or incomplete review scope: {document}')
            fingerprint = digest_value(review['fingerprint'])
            bindings = nonempty_list(review['bindings'])
        except INPUT_ERRORS as error:
            reason = f'Cannot validate historical review {document}. {error}'
            self._surface_errors[surface].append(reason)
            self._add_route(document, surface, document, (), reason=reason)
            return
        for binding in bindings:
            paths = set()
            declared = binding.get('witnesses') if isinstance(binding, dict) else None
            records = declared if isinstance(declared, list) else []
            try:
                paths = set(map(relative, nonempty_list(binding['files'])))
                covered.update(paths)
                nonempty_list(records)
                authority, mark, selector = nonempty_text(binding['authority']).partition('#')
                relative(authority)
                if not mark:
                    raise ValueError('A witness binding must name an authority field.')
                pointer_parts(selector)
            except INPUT_ERRORS as error:
                reason = f'Cannot validate a historical binding in {document}. {error}'
                errors.append(reason)
                if paths:
                    for path in paths:
                        self._path_errors[surface, path].append(reason)
                else:
                    self._surface_errors[surface].append(reason)
                for record in records:
                    try:
                        witness = relative(record['path'])
                    except INPUT_ERRORS:
                        continue
                    self._add_route(witness, surface, document, paths, witness=witness, reason=reason)
                continue
            for record in records:
                witness = None
                reasons = []
                try:
                    witness = relative(record['path'])
                    checks = self._witness_checks(witness, fingerprint, digest_value(record['sha256']),
                                                  binding['authority'], paths)
                except INPUT_ERRORS as error:
                    reason = f'Cannot validate a historical witness in {document}. {error}'
                    reasons.append(reason)
                    for path in paths:
                        self._path_errors[surface, path].append(reason)
                else:
                    for test, case, expected, covered_paths in checks:
                        if not covered_paths:
                            continue
                        status, actual, reason = self._test_status(test, case, expected)
                        check = {'test': test, 'case': case, 'authority': binding['authority'], 'witness': witness,
                                 'expectedTestSha256': expected, 'actualTestSha256': actual,
                                 'testPresent': test in self._paths, 'testStatus': status}
                        for path in covered_paths:
                            if check not in self._checks[surface, path]:
                                self._checks[surface, path].append(check)
                            if reason:
                                self._path_errors[surface, path].append(reason)
                        self._add_route(test, surface, document, covered_paths,
                                        witness=witness, reason=reason, check=check)
                        if reason:
                            reasons.append(reason)
                if witness is not None:
                    self._add_route(witness, surface, document, paths, witness=witness,
                                    reason=' '.join(sorted(set(reasons))) or None)
                errors.extend(reasons)
        self._add_route(document, surface, document, covered, reason=' '.join(sorted(set(errors))) or None)

    def for_path(self, path, surface):
        return _result(self._checks.get((surface, path), []),
                       self._path_errors.get((surface, path), []) + self._surface_errors.get(surface, []))

    def dependencies(self, path):
        return self._reverse.get(path, [])


def witness_index(read, paths, surfaces):
    return WitnessIndex(read, paths, surfaces)
