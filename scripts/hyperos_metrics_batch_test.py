#!/usr/bin/env python3
"""Behavioral regressions for actual HyperOS staging and boot repair."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from font_inventory import _read_metrics
import hyperos_metrics_batch as batch
import font_live_payload as live_payload


def font_file(path, top=700, points=(65,)):
    path.parent.mkdir(parents=True, exist_ok=True)
    fb = FontBuilder(1000, isTTF=True)
    cmap = {cp: 'A' if cp == 65 else f'u{cp:X}' for cp in points}
    order = ['.notdef', *cmap.values()]
    glyphs = {}
    for name in order:
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0)); pen.lineTo((500, 0)); pen.lineTo((500, top)); pen.closePath()
        glyphs[name] = pen.glyph()
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 0) for name in order})
    fb.setupHorizontalHeader(ascent=1600, descent=-600)
    fb.setupOS2(sTypoAscender=1600, sTypoDescender=-600, usWinAscent=1700, usWinDescent=700)
    fb.setupNameTable({'familyName': 'Fixture', 'styleName': 'Regular'})
    fb.setupPost(); fb.setupMaxp(); fb.save(path)


def slot(ascent=1100, descent=-350, win=1400, typo=1080, use_typo=True, head=None, upem=1000):
    result = {'metrics': {'upem': upem,
        'hhea': {'ascent': ascent, 'descent': descent, 'lineGap': 30},
        'os2': {'typoAscender': typo, 'typoDescender': -320, 'typoLineGap': 20,
                'winAscent': win, 'winDescent': 400, 'fsSelection': 128 if use_typo else 0}}}
    if head is not None:
        result['metrics']['head'] = dict(zip(('yMin', 'yMax'), head))
    return result


class HyperOSMetricsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.stage = self.module / '.luoshu-payload-next'
        self.fonts = self.stage / 'system/fonts'
        self.fonts.mkdir(parents=True)
        (self.module / 'config').mkdir()
        # The host may load FontTools only through the bundled pure-Python path.
        # Preserve that path separately before the Android entry point replaces it.
        self.env = {'LUOSHU_BUILD_KEY': 'fixture',
                    'LUOSHU_TEST_PYTHONPATH': os.pathsep.join(sys.path)}
        for part in batch.PARTS:
            root = self.root / 'stock' / part
            root.mkdir(parents=True)
            self.env[f'LUOSHU_{part.upper()}_FONTS_ROOT'] = str(root)
        self.env_patch = patch.dict(os.environ, self.env)
        self.env_patch.start(); self.addCleanup(self.env_patch.stop)
        font_file(self.fonts / '400.ttf')

    def inventory(self, slots):
        (self.module / 'config/device_font_inventory.json').write_text(json.dumps({
            'schema': 'device-font-inventory-v1', 'inventoryRevision': 1,
            'state': 'ready', 'buildKey': 'fixture', 'slots': slots}))
        for logical in slots:
            part, name = logical.split('/')[1], logical.split('/')[-1]
            (self.root / 'stock' / part / name).touch()

    def verified(self, name, part='product', weight=400, families=()):
        path = self.root / 'stock' / part / name
        font_file(path, points=(*range(32, 127), 0xA0))
        fmt, metrics = _read_metrics(path)
        return {'path': f'/{part}/fonts/{name}', 'source': 'verified-scan',
                'weight': weight, 'style': 'normal', 'faceIndex': 0,
                'families': list(families), 'format': fmt, 'metrics': metrics}

    def report(self):
        return {row['slot']: row for row in json.loads(
            (self.stage / '.luoshu-metrics-report.json').read_text())['slots']}

    def test_trusted_inventory_completes_oem_names_and_explicit_weights(self):
        # Names/styles match actual stock inventory omissions from Redmi/dali
        # OS3.0.303. Synthetic outlines avoid copying ROM fonts into the repo.
        cases = (('CarroisGothicSC-Regular.ttf', 'system', 400),
                 ('MiuiEx-Light.ttf', 'product', 300),
                 ('Interscaled-Medium.otf', 'product', 500),
                 ('ChamberiDisplay-Semibold.ttf', 'product', 600),
                 ('MiuiEx-Bold.ttf', 'product', 700),
                 ('Coca-ColaCareFontKaiTi.TTF', 'product', 400))
        tops = {300: 620, 400: 700, 500: 790, 600: 850, 700: 920}
        for weight, top in tops.items():
            font_file(self.fonts / f'{weight}.ttf', top)
        slots = {f'/{part}/fonts/{name}': self.verified(name, part, weight)
                 for name, part, weight in cases}
        slots['/system/fonts/CarroisGothicSC-Regular.ttf'].update(
            source='xml', families=['sans-serif-smallcaps'])
        self.inventory(slots)
        result = batch.build(self.module, self.stage, [])
        self.assertEqual(result['mapped'], len(cases))
        self.assertEqual(result['fallbackSlots'], 0)
        reports = self.report()
        for name, part, weight in cases:
            with TTFont(self.stage / part / 'fonts' / name) as font:
                self.assertEqual(font['glyf']['A'].yMax, tops[weight])
                self.assertEqual(font['hhea'].ascent, slots[f'/{part}/fonts/{name}']['metrics']['hhea']['ascent'])
            self.assertEqual(reports[f'/{part}/fonts/{name}']['slotSource'], 'stock-inventory')

    def test_unavailable_completion_weight_uses_selected_regular_source(self):
        self.inventory({'/product/fonts/MiuiEx-Bold.ttf': self.verified('MiuiEx-Bold.ttf', weight=700)})
        batch.build(self.module, self.stage, [])
        with TTFont(self.stage / 'product/fonts/MiuiEx-Bold.ttf') as font:
            self.assertEqual(font['glyf']['A'].yMax, 700)

    def test_inventory_completion_excludes_unsafe_faces_and_managed_symlinks(self):
        slots = {'/system/fonts/MiSansVF.ttf': slot()}
        names = ('Symbols.ttf', 'NovelUI.ttf', 'Roboto-Italic.ttf', 'NotoSansArabic.ttf',
                 'RobotoMono.ttf', 'Collection.ttf', 'OtherFace.ttf', 'GoogleSansManaged.ttf')
        for name in names:
            slots[f'/product/fonts/{name}'] = self.verified(name)
        slots['/product/fonts/NovelUI.ttf']['metrics'].pop('coverage')
        slots['/product/fonts/Collection.ttf']['format'] = 'TTC'
        slots['/product/fonts/OtherFace.ttf']['faceIndex'] = 1
        self.inventory(slots)
        managed = self.root / 'stock/product/GoogleSansManaged.ttf'
        managed.unlink(); managed.symlink_to(self.root / 'stock/product/NovelUI.ttf')
        result = batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        self.assertEqual(result['mapped'], 1)
        for name in names:
            self.assertFalse((self.stage / 'product/fonts' / name).exists(), name)

    def test_completion_uses_only_manifest_partitions_and_canonical_paths(self):
        slots = {'/system/fonts/MiSansVF.ttf': slot()}
        for part in ('vendor_custom', 'unrecorded', 'data'):
            root = self.root / 'stock' / part
            root.mkdir()
            os.environ[f'LUOSHU_{part.upper()}_FONTS_ROOT'] = str(root)
            slots[f'/{part}/fonts/NovelUI.ttf'] = self.verified('NovelUI.ttf', part)
        slots['/vendor_custom/fonts/subdir/Nested.ttf'] = self.verified('Nested.ttf', 'vendor_custom')
        slots['/vendor_custom/fonts//NovelUI.ttf'] = self.verified('NovelUI.ttf', 'vendor_custom')
        slots['/vendor_custom/fonts//NovelUI.ttf']['path'] = '/vendor_custom/fonts//NovelUI.ttf'
        slots['/vendor_custom/fonts/subdir/Nested.ttf']['path'] = '/vendor_custom/fonts/subdir/Nested.ttf'
        self.inventory(slots)
        (self.module / 'config/device_font_partitions.conf').write_text('vendor_custom\ndata\n../escape\n')
        result = batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        self.assertEqual(result['mapped'], 2)
        self.assertTrue((self.stage / 'vendor_custom/fonts/NovelUI.ttf').is_file())
        self.assertFalse((self.stage / 'unrecorded/fonts/NovelUI.ttf').exists())
        self.assertFalse((self.stage / 'data/fonts/NovelUI.ttf').exists())
        self.assertFalse((self.stage / 'vendor_custom/fonts/subdir/Nested.ttf').exists())

    def test_absent_or_invalid_stock_inventory_never_creates_completion_targets(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(),
                        '/product/fonts/NovelUI.ttf': self.verified('NovelUI.ttf')})
        (self.root / 'stock/product/NovelUI.ttf').unlink()
        self.assertEqual(batch.build(self.module, self.stage, ['MiSansVF.ttf'])['mapped'], 1)
        self.assertFalse((self.stage / 'product/fonts/NovelUI.ttf').exists())
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(),
                        '/product/fonts/NovelUI.ttf': self.verified('NovelUI.ttf')})
        config = self.module / 'config/device_font_inventory.json'
        data = json.loads(config.read_text())
        data['slots']['/product/fonts/NovelUI.ttf']['metrics']['hhea']['ascent'] = -1
        config.write_text(json.dumps(data))
        self.assertEqual(batch.build(self.module, self.stage, ['MiSansVF.ttf'])['mapped'], 1)
        self.assertFalse((self.stage / 'product/fonts/NovelUI.ttf').exists())
        data['buildKey'] = 'another-rom'; config.write_text(json.dumps(data))
        self.assertEqual(batch.build(self.module, self.stage, ['MiSansVF.ttf'])['fallbackSlots'], 1)
        self.assertFalse((self.stage / 'product/fonts/NovelUI.ttf').exists())

    def test_known_target_cannot_create_fonts_through_outside_partition_symlink(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(),
                        '/product/fonts/MiSansVF.ttf': slot()})
        outside = self.root / 'outside'; outside.mkdir()
        (self.stage / 'product').symlink_to(outside, target_is_directory=True)
        before = (self.fonts / '400.ttf').read_bytes()
        with self.assertRaisesRegex(ValueError, '隔离目录之外'):
            batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual((self.fonts / '400.ttf').read_bytes(), before)

    def test_generator_store_cannot_escape_staging(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot()})
        outside = self.root / 'outside'; outside.mkdir()
        (self.fonts / '.luoshu-font-store').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, '隔离目录之外'):
            batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.fonts / 'MiSansVF.ttf').exists())

    def test_report_publication_does_not_modify_a_linked_live_report(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot()})
        live = self.module / '.luoshu-payload'
        live.mkdir()
        sentinel = live / '.luoshu-metrics-report.json'
        sentinel.write_bytes(b'live-record-must-stay-unchanged')
        report = self.stage / '.luoshu-metrics-report.json'
        for link in ('symlink', 'hardlink', 'stale-temp-symlink', 'stale-temp-hardlink'):
            with self.subTest(link=link):
                report.unlink(missing_ok=True)
                leaf = report.with_name(report.name + f'.tmp.{os.getpid()}') if link.startswith('stale-temp') else report
                leaf.unlink(missing_ok=True)
                if link.endswith('symlink'):
                    leaf.symlink_to(sentinel)
                else:
                    os.link(sentinel, leaf)
                batch.build(self.module, self.stage, ['MiSansVF.ttf'])
                self.assertEqual(sentinel.read_bytes(), b'live-record-must-stay-unchanged')
                self.assertFalse(report.is_symlink())
                self.assertNotEqual(report.stat().st_ino, sentinel.stat().st_ino)
                self.assertEqual(list(self.report()), ['/system/fonts/MiSansVF.ttf'])
                leaf.unlink(missing_ok=True)

    def test_stale_alias_temp_cannot_mutate_a_live_inode(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot()})
        live = self.module / '.luoshu-payload'; live.mkdir()
        sentinel = live / 'MiSansVF.ttf'
        sentinel.write_bytes(b'live-font-must-stay-unchanged')
        target = self.fonts / 'MiSansVF.ttf'
        temporary = target.with_name(target.name + f'.tmp.{os.getpid()}')
        for link in ('symlink', 'hardlink'):
            with self.subTest(link=link):
                if link == 'symlink':
                    temporary.symlink_to(sentinel)
                else:
                    os.link(sentinel, temporary)
                batch.build(self.module, self.stage, ['MiSansVF.ttf'])
                self.assertEqual(sentinel.read_bytes(), b'live-font-must-stay-unchanged')
                self.assertFalse(temporary.exists())
                with TTFont(target) as font:
                    self.assertIn(65, font.getBestCmap())

    def test_rejects_module_live_and_live_descendant_roots(self):
        for target in (self.module, self.module / '.luoshu-payload',
                       self.module / '.luoshu-payload/subdir'):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, '本次启动'):
                batch.build(self.module, target, [])

    def test_completed_dynamic_slot_survives_live_copy_and_atomic_bind_visibility(self):
        stock_root = self.root / 'stock/vendor_custom'; stock_root.mkdir()
        os.environ['LUOSHU_VENDOR_CUSTOM_FONTS_ROOT'] = str(stock_root)
        logical = '/vendor_custom/fonts/NovelUI.ttf'
        self.inventory({logical: self.verified('NovelUI.ttf', 'vendor_custom')})
        (self.module / 'config/device_font_partitions.conf').write_text('vendor_custom\n')
        batch.build(self.module, self.stage, [])
        generation = live_payload.prepare(self.stage, self.root / 'live-cache', 'host-fixture-boot',
                                          self.root / 'live-temp')
        mapped = self.stage / 'vendor_custom/fonts/NovelUI.ttf'
        copied = generation / 'vendor_custom/fonts/NovelUI.ttf'
        self.assertEqual(copied.read_bytes(), mapped.read_bytes())
        self.assertNotEqual(copied.stat().st_ino, mapped.stat().st_ino)
        visible = self.root / 'visible'; visible.mkdir()
        font_file(visible / 'NovelUI.ttf', top=123)
        state = self.root / 'mount-state'
        calls = self.root / 'bind-calls'
        # Run the unchanged atomic enumeration/bind/visibility implementations.
        # Its kernel mount command is explicitly replaced by an isolated copy.
        code = r'''
. "$1"
_luoshu_self_state_root() { printf '%s\n' "$FIXTURE_STATE"; }
_luoshu_mount_cmd() {
    [ "$1" = -o ] && [ "$2" = bind ] || return 1
    printf '%s\n' "$3" >> "$FIXTURE_CALLS"
    cp "$3" "$4"
}
_lsme_mount_list="$FIXTURE_JOURNAL"
_luoshu_atomic_bind_tree "$FIXTURE_SOURCE" "$FIXTURE_VISIBLE" || exit 1
_luoshu_atomic_tree_visible "$FIXTURE_SOURCE" "$FIXTURE_VISIBLE" bind
'''
        result = subprocess.run(['sh', '-c', code, 'sh', str(ROOT / 'common/mount_self_atomic.sh')],
            env={**os.environ, 'FIXTURE_STATE': str(state), 'FIXTURE_CALLS': str(calls),
                 'FIXTURE_JOURNAL': str(self.root / 'mount-journal'),
                 'FIXTURE_SOURCE': str(copied.parent), 'FIXTURE_VISIBLE': str(visible)},
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls.read_text().splitlines(), [str(copied)])
        self.assertEqual((visible / 'NovelUI.ttf').read_bytes(), mapped.read_bytes())

    def test_full_stock_contract_and_glyphs_unchanged(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot()})
        with patch.object(TTFont, 'getGlyphSet', side_effect=AssertionError('outline rebuild')):
            result = batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        self.assertEqual(result, {'mapped': 1, 'generated': 1, 'fallbackSlots': 0})
        report = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())
        self.assertEqual(report['slots'][0]['metricsSource'], 'stock')
        self.assertEqual(report['slots'][0]['slot'], '/system/fonts/MiSansVF.ttf')
        with TTFont(self.fonts / 'MiSansVF.ttf') as out, TTFont(self.fonts / '400.ttf') as src:
            self.assertEqual((out['hhea'].ascent, out['hhea'].descent, out['hhea'].lineGap), (1100, -350, 30))
            self.assertEqual((out['OS/2'].sTypoAscender, out['OS/2'].sTypoLineGap), (1080, 20))
            self.assertEqual(out['OS/2'].usWinAscent, 1400)
            self.assertEqual(out['glyf'].compile(out), src['glyf'].compile(src))
            self.assertEqual(out['head'].yMax, src['head'].yMax)

    def test_full_contract_cache_and_multiweight(self):
        font_file(self.fonts / '700.ttf', 900)
        self.inventory({'/system/fonts/Roboto-Regular.ttf': slot(),
                        '/product/fonts/Roboto-Regular.ttf': slot(win=1500, use_typo=False),
                        '/system/fonts/Roboto-Bold.ttf': slot(),
                        '/system/fonts/MiSansVF.ttf': slot()})
        result = batch.build(self.module, self.stage, ['Roboto-Regular.ttf', 'Roboto-Bold.ttf', 'MiSansVF.ttf'])
        self.assertEqual(result['generated'], 3)
        with TTFont(self.stage / 'product/fonts/Roboto-Regular.ttf') as font:
            self.assertEqual(font['OS/2'].usWinAscent, 1500)
            self.assertFalse(font['OS/2'].fsSelection & 128)
        with TTFont(self.fonts / 'Roboto-Bold.ttf') as font:
            self.assertEqual(font['head'].yMax, 900)

    def test_no_cascade_when_alias_is_source(self):
        (self.fonts / '400.ttf').rename(self.fonts / 'MiSansVF.ttf')
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(),
                        '/product/fonts/MiSansVF.ttf': slot()})
        result = batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        self.assertEqual(result['generated'], 1)

    def test_stage_completion_releases_temporary_fonts_after_linking(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(),
                        '/product/fonts/MiSansVF.ttf': slot()})
        for _ in range(3):
            batch.build(self.module, self.stage, ['MiSansVF.ttf'])
            store = self.fonts / '.luoshu-font-store'
            self.assertEqual(list(store.glob('hyperos-metrics-*')), [])
            # Removing generator names must leave both partition aliases usable.
            for part in ('system', 'product'):
                with TTFont(self.stage / part / 'fonts/MiSansVF.ttf') as font:
                    self.assertEqual(font['hhea'].ascent, 1100)
                    self.assertIn(65, font.getBestCmap())

    def test_failed_stage_completion_releases_temporary_fonts(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot()})
        with patch.object(batch, 'write_metrics', side_effect=ValueError('bad source')):
            with self.assertRaisesRegex(ValueError, 'bad source'):
                batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        self.assertEqual(list((self.fonts / '.luoshu-font-store').glob('hyperos-metrics-*')), [])

    def test_latin_bitmap_policy_does_not_leak_to_main_or_clock(self):
        slots = {f'/system/fonts/{name}': slot(use_typo=False, head=(-430, 1100))
                 for name in ('Roboto-Regular.ttf', 'MiSansVF.ttf', 'MiClock.otf')}
        self.inventory(slots)
        batch.build(self.module, self.stage, [Path(logical).name for logical in slots])
        for name, expected in (('Roboto-Regular.ttf', -350), ('MiSansVF.ttf', -430),
                               ('MiClock.otf', -430)):
            with self.subTest(name=name), TTFont(self.fonts / name) as font:
                self.assertEqual(font['head'].yMin, expected)
                self.assertEqual(font['head'].yMax, 1100)
                self.assertEqual(font['hhea'].descent, -350)
        data = {'mainSlotPath': '/system/fonts/Roboto-Regular.ttf', 'slots': slots}
        contract = batch.contract_for_slot(data, data['mainSlotPath'])
        self.assertFalse(batch.bitmap_bottom_slot(data, data['mainSlotPath'], contract))

    def test_latin_descenders_guard_against_new_bitmap_clipping(self):
        source = self.fonts / '400.ttf'
        with TTFont(source) as font:
            pen = TTGlyphPen(None)
            pen.moveTo((0, -500)); pen.lineTo((500, -500))
            pen.lineTo((500, 700)); pen.closePath()
            font['glyf']['A'] = pen.glyph()
            font.save(source)
        self.inventory({'/system/fonts/Roboto-Regular.ttf': slot(use_typo=False, head=(-550, 1100))})
        batch.build(self.module, self.stage, ['Roboto-Regular.ttf'])
        with TTFont(self.fonts / 'Roboto-Regular.ttf') as font:
            self.assertEqual(font['head'].yMin, -550)
        report = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())['slots'][0]
        self.assertEqual(report['bitmapBaselineReason'], 'latin-descender-would-clip')
        self.assertEqual(report['bitmapBaselineCorrection'], 0)

    def test_padded_layout_frame_uses_each_stock_slot_and_scales_units(self):
        self.inventory({'/system/fonts/MiClock.otf': slot(head=(-201, 880)),
                        '/product/fonts/MiClock.otf': slot(head=(-555, 2163), upem=2048)})
        with patch.object(TTFont, 'getGlyphSet', side_effect=AssertionError('outline rebuild')):
            result = batch.build(self.module, self.stage, ['MiClock.otf'])
        self.assertEqual(result['generated'], 2, 'head must participate in slot cache key')
        for part, expected in (('system', (-201, 880)), ('product', (-271, 1056))):
            with TTFont(self.stage / part / 'fonts/MiClock.otf') as font:
                self.assertEqual((font['head'].yMin, font['head'].yMax), expected)
                with TTFont(self.fonts / '400.ttf') as source:
                    self.assertEqual(font.reader['glyf'], source.reader['glyf'])
        report = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())
        self.assertTrue(all(entry['layoutBoundsSource'] == 'stock' for entry in report['slots']))

    def test_different_head_with_identical_line_metrics_cannot_share_alias(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(head=(-300, 1100)),
                        '/system/fonts/MiClock.otf': slot(head=(-201, 880))})
        result = batch.build(self.module, self.stage, ['MiSansVF.ttf', 'MiClock.otf'])
        self.assertEqual(result['generated'], 2)
        self.assertNotEqual((self.fonts / 'MiSansVF.ttf').stat().st_ino,
                            (self.fonts / 'MiClock.otf').stat().st_ino)

    def test_zero_and_shallow_stock_descent_do_not_trigger_generic_fallback(self):
        for descent in (0, -1, -20):
            with self.subTest(descent=descent):
                self.inventory({'/system/fonts/MiClock.otf': slot(descent=descent, head=(100, 700))})
                result = batch.build(self.module, self.stage, ['MiClock.otf'])
                self.assertEqual(result['fallbackSlots'], 0)
                with TTFont(self.fonts / 'MiClock.otf') as font:
                    self.assertEqual(font['hhea'].descent, descent)
                    self.assertEqual(font['head'].yMin, 100)

    def test_missing_or_malformed_head_keeps_line_metrics_and_reports_gap(self):
        for head in (None, (700, 100), (-99999, 800)):
            with self.subTest(head=head):
                self.inventory({'/system/fonts/MiClock.otf': slot(head=head)})
                self.assertEqual(batch.build(self.module, self.stage, ['MiClock.otf'])['fallbackSlots'], 0)
                report = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())['slots'][0]
                self.assertEqual(report['layoutBoundsSource'], 'source')
                self.assertEqual(report['outputHead'], report['sourceHead'])

    def test_missing_inventory_reports_fallback_and_bad_source_fails(self):
        (self.root / 'stock/system/MiSansVF.ttf').touch()
        result = batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        self.assertEqual(result['fallbackSlots'], 1)
        report = json.loads((self.stage / '.luoshu-metrics-report.json').read_text())
        self.assertEqual(report['slots'][0]['metricsSource'], 'fallback')
        (self.fonts / '400.ttf').write_bytes(b'corrupt')
        with self.assertRaises(Exception):
            batch.build(self.module, self.stage, ['MiSansVF.ttf'])

    def test_boot_repair_preserves_partition_contract(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(),
                        '/product/fonts/MiSansVF.ttf': slot(ascent=850, descent=-150)})
        batch.build(self.module, self.stage, ['MiSansVF.ttf'])
        target = self.stage / 'product/fonts/MiSansVF.ttf'
        before = target.read_bytes()
        subprocess.run(['sh', '-c', '. "$1"; luoshu_hyperos_clock_payload_ensure', 'sh',
                        str(ROOT / 'common/legacy_v14_4/hyperos_clock_compat.sh')],
                       env={**os.environ, 'MODDIR': str(self.module), 'IS_HYPEROS': 'true',
                            'LUOSHU_HYPEROS_CLOCK_PAYLOAD_ROOT': str(self.stage)}, check=True)
        self.assertEqual(target.read_bytes(), before)

    def test_reject_live_payload(self):
        with self.assertRaisesRegex(ValueError, '本次启动'):
            batch.build(self.module, self.module / '.luoshu-payload', ['MiSansVF.ttf'])

    def test_stage_covers_the_same_dynamic_slots_as_boot(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(),
                        '/product/fonts/MiSansDisplayVF.ttf': slot(ascent=850, descent=-150),
                        '/product/fonts/XiaomiSansVF.otf': slot(ascent=900, descent=-200)})
        common = self.module / 'common'
        (common / 'python/bin').mkdir(parents=True)
        (common / 'legacy_v14_4').mkdir()
        (self.module / 'module.prop').touch()
        for relative in ('hyperos_metrics_batch.py', 'font_metrics_normalize.py',
                         'legacy_v14_4/hyperos_full_coverage.sh',
                         'legacy_v14_4/hyperos_clock_compat.sh'):
            (common / relative).write_bytes((ROOT / 'common' / relative).read_bytes())
        (common / 'hyperos_global.sh').write_text('''
_hyperos_core_files() { echo MiSansVF.ttf; }
_hyperos_weight_files() { :; }
_hyperos_upright_ui_files() { :; }
_hyperos_clock_ui_files() { :; }
''')
        launcher = common / 'python/bin/luoshu-python'
        launcher.write_text('#!/bin/sh\nunset PYTHONHOME LD_LIBRARY_PATH\n'
                            'PYTHONPATH="$LUOSHU_TEST_PYTHONPATH" '
                            'exec "$LUOSHU_TEST_PYTHON" "$@"\n')
        launcher.chmod(0o755)
        result = subprocess.run(['sh', str(ROOT / 'common/hyperos_stage_complete.sh'), str(self.stage)],
            env={**os.environ, 'LUOSHU_REAL_MODDIR': str(self.module),
                 'LUOSHU_TEST_PYTHON': sys.executable}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name, ascent in (('MiSansDisplayVF.ttf', 850), ('XiaomiSansVF.otf', 900)):
            target = self.stage / 'product/fonts' / name
            self.assertTrue(target.exists(), 'boot-only aliases bypass per-slot metrics')
            with TTFont(target) as font:
                self.assertEqual(font['hhea'].ascent, ascent)

    def test_stage_failure_propagates_through_both_callers(self):
        helper = self.module / 'common/hyperos_stage_complete.sh'
        helper.parent.mkdir(parents=True)
        helper.write_text('printf "called\\n" >> "$TEST_CALLS"\nexit 7\n')
        marker = self.root / 'calls'
        for relative, function in (
            ('common/legacy_v14_4/font_switch_safe.sh', 'stage_hyperos_complete'),
            ('common/legacy_v14_4/mix_router.sh', 'complete_hyperos_stage'),
        ):
            source = (ROOT / relative).read_text()
            start = source.index(function + '() {')
            code = source[start:source.index('\n}', start) + 2]
            result = subprocess.run(['sh', '-c', '. "$1"\n' + code + '\ngetprop() { echo HyperOS; }\n' + function,
                                     'sh', str(ROOT / 'common/legacy_v14_4/mix_phase_timing.sh')],
                env={**os.environ, 'IS_HYPEROS': 'true', 'MODDIR': str(self.module),
                     'REALMOD': str(self.module), 'LOG_FILE': str(self.root / 'log'),
                     'STAGE_PAYLOAD': str(self.stage), 'MIX_STAGE': str(self.stage),
                     'TEST_CALLS': str(marker)})
            self.assertNotEqual(result.returncode, 0, relative)
        self.assertEqual(marker.read_text().splitlines(), ['called', 'called'])

    def test_shell_entry_uses_one_python_process(self):
        self.inventory({'/system/fonts/MiSansVF.ttf': slot(),
                        '/product/fonts/MiSansVF.ttf': slot()})
        common = self.module / 'common'
        (common / 'python/bin').mkdir(parents=True)
        (self.module / 'module.prop').touch()
        for name in ('hyperos_metrics_batch.py', 'font_metrics_normalize.py'):
            (common / name).write_bytes((ROOT / 'common' / name).read_bytes())
        (common / 'hyperos_global.sh').write_text('''
_hyperos_core_files() { echo MiSansVF.ttf; }
_hyperos_weight_files() { :; }
_hyperos_upright_ui_files() { :; }
_hyperos_clock_ui_files() { :; }
''')
        launcher = common / 'python/bin/luoshu-python'
        launcher.write_text('#!/bin/sh\nprintf "launch\\n" >> "$LUOSHU_TEST_LAUNCHES"\n'
                            'unset PYTHONHOME LD_LIBRARY_PATH\n'
                            'PYTHONPATH="$LUOSHU_TEST_PYTHONPATH" '
                            'exec "$LUOSHU_TEST_PYTHON" "$@"\n')
        launcher.chmod(0o755)
        launches = self.root / 'launches'
        command = ['sh', str(ROOT / 'common/hyperos_stage_complete.sh'), str(self.stage)]
        env = {**os.environ, 'LUOSHU_REAL_MODDIR': str(self.module),
               'LUOSHU_TEST_LAUNCHES': str(launches), 'LUOSHU_TEST_PYTHON': sys.executable}
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['mapped'], 2)
        self.assertEqual(launches.read_text().splitlines(), ['launch'])
        (self.fonts / '400.ttf').write_bytes(b'corrupt')
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('HyperOS 字体处理失败', result.stderr)


if __name__ == '__main__':
    unittest.main()
