"""Control alignment getter contracts; synthetic geometry is not native execution proof."""
import copy
import unittest
from test_native_control_icons import ASSET, draft, fixture


def between_fixture(placement='after'):
    parent, label, icon, style = fixture(placement)
    style.update(justifyContent='space-between', paddingX=16, paddingY=13)
    style['icon']['gap'] = 12
    parent.update(width=292, height=46, itemSpacing=12, primaryAxisAlignItems='SPACE_BETWEEN',
                  paddingLeft=16, paddingRight=16, paddingTop=13, paddingBottom=13)
    label.update(x=16 if placement == 'after' else 178, y=13, width=98, height=20)
    icon.update(x=258 if placement == 'after' else 16, y=14)
    return parent, label, icon, style


class ControlAlignment(unittest.TestCase):
    def findings(self, values):
        return draft._native_control_icon_findings(*values, 'control', {'arrow': ASSET})

    def test_actual_quiet_seat_endpoint_geometry_uses_minimum_gap(self):
        # Observed desktop CTA: 292x46, label x=16, icon x=258, CSS gap=12.
        for placement in ('before', 'after'):
            self.assertEqual(self.findings(between_fixture(placement)), [])

    def test_wrong_alignment_order_gap_padding_and_missing_icon_fail(self):
        for mutate in (
            lambda p,l,i,s: p.update(primaryAxisAlignItems='CENTER'),
            lambda p,l,i,s: p.pop('primaryAxisAlignItems'),
            lambda p,l,i,s: s['icon'].update(placement='before'),
            lambda p,l,i,s: i.update(x=120),
            lambda p,l,i,s: l.update(x=20),
            lambda p,l,i,s: i.update(y=8),
            lambda p,l,i,s: l.update(y=8),
            lambda p,l,i,s: p.update(itemSpacing=0),
            lambda p,l,i,s: p.update(paddingLeft=0),
            lambda p,l,i,s: i.clear(),
        ):
            values = between_fixture()
            mutate(*values)
            self.assertTrue(self.findings(values))

    def test_default_center_remains_valid_without_readback_alignment(self):
        values = fixture()
        self.assertEqual(self.findings(values), [])
        values[-1]['justifyContent'] = 'center'
        self.assertTrue(self.findings(values))
        values[0].update(primaryAxisAlignItems='CENTER', paddingLeft=20, paddingRight=20, paddingTop=12, paddingBottom=12)
        self.assertEqual(self.findings(values), [])

    def test_optional_enum_never_injects_defaults(self):
        assets = {'arrow': {'path': 'arrow.png', 'sha256': 'a' * 64}}
        legacy = fixture()[-1]
        before = copy.deepcopy(legacy)
        draft.check_control_icon(legacy, assets, 'control')
        self.assertEqual(legacy, before)
        for invalid in (None, [], {}, False, 'SPACE_BETWEEN', 'left'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                draft.check_control_icon(dict(legacy, justifyContent=invalid), assets, 'control')
        for valid in ('center', 'space-between'):
            draft.check_control_icon(dict(legacy, justifyContent=valid), assets, 'control')
        text_only = {key: value for key, value in legacy.items() if key != 'icon'}
        draft.check_control_icon(dict(text_only, justifyContent='center'), assets, 'control')
        with self.assertRaisesRegex(ValueError, 'requires a label and icon'):
            draft.check_control_icon(dict(text_only, justifyContent='space-between'), assets, 'control')


if __name__ == '__main__':
    unittest.main()
