#!/usr/bin/env python3
"""Read-only topology accounting; no FontTools, device or private App reads."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

import font_role_shadow
import luoshu_coverage_audit as audit


# Sanitized 2026-10-05 HyperOS diagnostic: one row per real logical path.
# Columns: path, classifier role, semantic/coverage inputs, old replacement,
# actual kept reason. Only system font topology is retained; no App/process,
# device identifier, source file, timestamps or chat data are embedded.
DEVICE_ROWS = r'''
["/product/fonts/BebasNeue-Mono.otf","monospace",{},null,null]
["/product/fonts/BeihaibeiSC-Regular.ttf","unknown-protected",{"metrics":{"coverage":{"digitCount":10,"hanCount":71,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/BeihaibeiSC-Regular.ttf","role":"broad-text"},null]
["/product/fonts/BeihaibeiTC-Regular.ttf","unknown-protected",{"metrics":{"coverage":{"digitCount":10,"hanCount":71,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/BeihaibeiTC-Regular.ttf","role":"broad-text"},null]
["/product/fonts/C800.ttf","latin",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/C800.ttf","role":"latin"},null]
["/product/fonts/ChamberiDisplay-Italic.otf","unknown-protected",{},{"path":"/product/fonts/ChamberiDisplay-Italic.otf","role":"broad-text"},null]
["/product/fonts/ChamberiDisplay-Semibold.ttf","latin",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/ChamberiDisplay-Semibold.ttf","role":"latin"},null]
["/product/fonts/Coca-ColaCareFontKaiTi.TTF","unknown-protected",{"metrics":{"coverage":{"digitCount":10,"hanCount":6777,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/Coca-ColaCareFontKaiTi.TTF","role":"broad-text"},null]
["/product/fonts/CommutersSansMono.otf","monospace",{},null,null]
["/product/fonts/DelaGothicOne-HZ.otf","symbol-icon",{},null,null]
["/product/fonts/DelaGothicOne.otf","symbol-icon",{},null,null]
["/product/fonts/FZFWZhuZiAYuanJWB.TTF","unknown-protected",{"metrics":{"coverage":{"digitCount":10,"hanCount":7423,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/FZFWZhuZiAYuanJWB.TTF","role":"broad-text"},null]
["/product/fonts/GulfsDisplay-ExtraExpandedItalic.otf","unknown-protected",{},{"path":"/product/fonts/GulfsDisplay-ExtraExpandedItalic.otf","role":"broad-text"},null]
["/product/fonts/InterMono-SemiBold.otf","monospace",{},null,null]
["/product/fonts/Interscaled-Medium.otf","latin",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/Interscaled-Medium.otf","role":"latin"},null]
["/product/fonts/Interscaled-Regular.otf","latin",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/Interscaled-Regular.otf","role":"latin"},null]
["/product/fonts/MiClock.otf","clock",{"metrics":{"coverage":{"digitCount":10,"hanCount":19,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiClock.otf","role":"clock"},null]
["/product/fonts/MiClockMono.otf","clock",{"metrics":{"coverage":{"digitCount":10,"hanCount":19,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiClockMono.otf","role":"clock"},null]
["/product/fonts/MiClockThin.otf","clock",{"metrics":{"coverage":{"digitCount":10,"hanCount":20,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiClockThin.otf","role":"clock"},null]
["/product/fonts/MiClockTibetan-Thin.ttf","clock",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiClockTibetan-Thin.ttf","role":"clock"},null]
["/product/fonts/MiClockUyghur-Thin.ttf","clock",{"metrics":{"coverage":{"digitCount":10,"hanCount":20,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiClockUyghur-Thin.ttf","role":"clock"},null]
["/product/fonts/MiSansArabicVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansBengaliVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansC_3.005.ttf","unknown-protected",{"metrics":{"coverage":{"digitCount":10,"hanCount":20,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiSansC_3.005.ttf","role":"broad-text"},null]
["/product/fonts/MiSansCondensed2T.ttf","unknown-protected",{"metrics":{"coverage":{"digitCount":10,"hanCount":35,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiSansCondensed2T.ttf","role":"broad-text"},null]
["/product/fonts/MiSansDevanagariVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansGujaratiVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansGurmukhiVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansJapaneseVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansKannadaVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansKhmerVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansKoreanVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansL3.otf","cjk",{"metrics":{"coverage":{"digitCount":0,"hanCount":60123,"hasDigits":false,"hasHan":true,"hasLatin":false,"latinCount":0}}},{"path":"/product/fonts/MiSansL3.otf","role":"cjk"},null]
["/product/fonts/MiSansLaoVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansLatinVF.ttf","latin",{"metrics":{"coverage":{"digitCount":10,"hanCount":1,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiSansLatinVF.ttf","role":"latin"},null]
["/product/fonts/MiSansMalayalamVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansMyanmarVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansOdiaVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansRoundedSC.ttf","unknown-protected",{"metrics":{"coverage":{"digitCount":10,"hanCount":71,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiSansRoundedSC.ttf","role":"broad-text"},null]
["/product/fonts/MiSansRoundedTC.ttf","unknown-protected",{"metrics":{"coverage":{"digitCount":10,"hanCount":71,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiSansRoundedTC.ttf","role":"broad-text"},null]
["/product/fonts/MiSansTCVF.ttf","unknown-protected",{"metrics":{"coverage":{"digitCount":10,"hanCount":13079,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiSansTCVF.ttf","role":"broad-text"},null]
["/product/fonts/MiSansTamilVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansTeluguVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansThaiVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansTibetanVF.ttf","special-fallback",{},null,null]
["/product/fonts/MiSansVF.ttf","unknown-protected",{"metrics":{"coverage":{"digitCount":10,"hanCount":27782,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiSansVF.ttf","role":"broad-text"},null]
["/product/fonts/MiSerifSCVF.ttf","serif",{},null,null]
["/product/fonts/MiSerifTCVF.ttf","serif",{},null,null]
["/product/fonts/MichromaMono.otf","monospace",{},null,null]
["/product/fonts/MitypeClock.otf","clock",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":false,"latinCount":0}}},{"path":"/product/fonts/MitypeClock.otf","role":"clock"},null]
["/product/fonts/MitypeClockMono.otf","clock",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":false,"latinCount":0}}},{"path":"/product/fonts/MitypeClockMono.otf","role":"clock"},null]
["/product/fonts/MitypeMonoVF.ttf","clock",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":false,"latinCount":0}}},{"path":"/product/fonts/MitypeMonoVF.ttf","role":"clock"},null]
["/product/fonts/MitypeVF.ttf","clock",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":false,"latinCount":0}}},{"path":"/product/fonts/MitypeVF.ttf","role":"clock"},null]
["/product/fonts/MiuiEx-Bold.ttf","latin",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiuiEx-Bold.ttf","role":"latin"},null]
["/product/fonts/MiuiEx-Light.ttf","latin",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiuiEx-Light.ttf","role":"latin"},null]
["/product/fonts/MiuiEx-Regular.ttf","latin",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/MiuiEx-Regular.ttf","role":"latin"},null]
["/product/fonts/NeumaticCompressed.otf","unknown-protected",{"metrics":{"coverage":{"digitCount":10,"hanCount":9,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/NeumaticCompressed.otf","role":"broad-text"},null]
["/product/fonts/Qinghe.otf","unknown-protected",{"metrics":{"coverage":{"digitCount":10,"hanCount":9170,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/product/fonts/Qinghe.otf","role":"broad-text"},null]
["/product/fonts/SilkSerif-Regular.ttf","serif",{},null,null]
["/system/fonts/AndroidClock.ttf","clock",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":false,"latinCount":0}}},{"path":"/system/fonts/AndroidClock.ttf","role":"clock"},null]
["/system/fonts/CarroisGothicSC-Regular.ttf","ui-sans",{"families":["sans-serif-smallcaps"],"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"sans-serif-smallcaps"}}]},{"path":"/system/fonts/CarroisGothicSC-Regular.ttf","role":"ui-sans"},null]
["/system/fonts/ComingSoon.ttf","special-fallback",{"families":["casual"],"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"casual"}}]},{"path":"/system/fonts/ComingSoon.ttf","role":"special-fallback","mode":"partial-stock","asciiLettersReplaced":52,"asciiDigitsReplaced":10},null]
["/system/fonts/CutiveMono.ttf","monospace",{"families":["courier","courier new","serif-monospace"],"xmlRefs":[{"familyAttributes":{"name":"serif-monospace"}}]},{"path":"/system/fonts/CutiveMono.ttf","role":"monospace","mode":"partial-stock","asciiLettersReplaced":52,"asciiDigitsReplaced":10},null]
["/system/fonts/DancingScript-Regular.ttf","special-fallback",{"families":["cursive"],"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"cursive"}}]},null,"partial-stock-variable-unsupported"]
["/system/fonts/DroidSans-Bold.ttf","latin",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}}},{"path":"/system/fonts/DroidSans-Bold.ttf","role":"latin"},null]
["/system/fonts/DroidSans.ttf","latin",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}}},{"path":"/system/fonts/DroidSans.ttf","role":"latin"},null]
["/system/fonts/DroidSansMono.ttf","monospace",{"families":["monaco","monospace","sans-serif-monospace"],"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"monospace"}}]},{"path":"/system/fonts/DroidSansMono.ttf","role":"monospace","mode":"partial-stock","asciiLettersReplaced":52,"asciiDigitsReplaced":10},null]
["/system/fonts/MiSansArabicVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Arab"}}]},null,null]
["/system/fonts/MiSansBengaliVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Beng"}}]},null,null]
["/system/fonts/MiSansDevanagariVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Deva"}}]},null,null]
["/system/fonts/MiSansGujaratiVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Gujr"}}]},null,null]
["/system/fonts/MiSansGurmukhiVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Guru"}}]},null,null]
["/system/fonts/MiSansJapaneseVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"ja"}}]},null,null]
["/system/fonts/MiSansKannadaVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Knda"}}]},null,null]
["/system/fonts/MiSansKhmerVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Khmr"}}]},null,null]
["/system/fonts/MiSansKoreanVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"ko"}}]},null,null]
["/system/fonts/MiSansL3.otf","cjk",{"metrics":{"coverage":{"digitCount":0,"hanCount":60123,"hasDigits":false,"hasHan":true,"hasLatin":false,"latinCount":0}},"xmlRefs":[{"familyAttributes":{"lang":"zh"}}]},{"path":"/system/fonts/MiSansL3.otf","role":"cjk"},null]
["/system/fonts/MiSansLaoVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Laoo"}}]},null,null]
["/system/fonts/MiSansLatinVF.ttf","latin",{"metrics":{"coverage":{"digitCount":10,"hanCount":1,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}}},{"path":"/system/fonts/MiSansLatinVF.ttf","role":"latin"},null]
["/system/fonts/MiSansMalayalamVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mlym"}}]},null,null]
["/system/fonts/MiSansMyanmarVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mymr"}}]},null,null]
["/system/fonts/MiSansOdiaVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Orya"}}]},null,null]
["/system/fonts/MiSansTCVF.ttf","cjk",{"metrics":{"coverage":{"digitCount":10,"hanCount":13079,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"lang":"zh-Hant,zh-Bopo"}}]},{"path":"/system/fonts/MiSansTCVF.ttf","role":"cjk"},null]
["/system/fonts/MiSansTamilVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Taml"}}]},null,null]
["/system/fonts/MiSansTeluguVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Telu"}}]},null,null]
["/system/fonts/MiSansThaiVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Thai"}}]},null,null]
["/system/fonts/MiSansTibetanVF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Tibt"}}]},null,null]
["/system/fonts/MiSansVF.ttf","cjk",{"families":["arial","helvetica","mipro-bold","mipro-demibold","mipro-extralight","mipro-heavy","mipro-light","mipro-medium","mipro-normal","mipro-semibold","mipro-thin","miui-bold","miui-light","miui-thin","sans-serif","sans-serif-black","sans-serif-light","sans-serif-medium","sans-serif-thin","tahoma","verdana"],"metrics":{"coverage":{"digitCount":10,"hanCount":27782,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"sans-serif"}},{"familyAttributes":{"lang":"zh-Hans"}}]},{"path":"/system/fonts/MiSansVF.ttf","role":"cjk"},null]
["/system/fonts/MiSansVF_Overlay.ttf","unknown-protected",{},null,null]
["/system/fonts/NotoColorEmoji.ttf","emoji",{"xmlRefs":[{"familyAttributes":{"lang":"und-Zsye"}}]},null,null]
["/system/fonts/NotoColorEmojiFlags.ttf","emoji",{"xmlRefs":[{"familyAttributes":{"lang":"und-Zsye"}}]},null,null]
["/system/fonts/NotoNaskhArabic-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Arab","variant":"elegant"}}]},null,null]
["/system/fonts/NotoNaskhArabic-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Arab","variant":"elegant"}}]},null,null]
["/system/fonts/NotoNaskhArabicUI-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Arab","variant":"compact"}}]},null,null]
["/system/fonts/NotoNaskhArabicUI-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Arab","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansAdlam-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Adlm"}}]},null,null]
["/system/fonts/NotoSansAhom-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Ahom"}}]},null,null]
["/system/fonts/NotoSansAnatolianHieroglyphs-Regular.otf","symbol-icon",{"xmlRefs":[{"familyAttributes":{"lang":"und-Hluw"}}]},null,null]
["/system/fonts/NotoSansArmenian-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Armn"}}]},null,null]
["/system/fonts/NotoSansAvestan-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Avst"}}]},null,null]
["/system/fonts/NotoSansBalinese-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Bali"}}]},null,null]
["/system/fonts/NotoSansBamum-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Bamu"}}]},null,null]
["/system/fonts/NotoSansBassaVah-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Bass"}}]},null,null]
["/system/fonts/NotoSansBatak-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Batk"}}]},null,null]
["/system/fonts/NotoSansBengali-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Beng","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansBengaliUI-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Beng","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansBhaiksuki-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Bhks"}}]},null,null]
["/system/fonts/NotoSansBrahmi-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Brah"}}]},null,null]
["/system/fonts/NotoSansBuginese-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Bugi"}}]},null,null]
["/system/fonts/NotoSansBuhid-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Buhd"}}]},null,null]
["/system/fonts/NotoSansCJK-Regular.ttc","special-fallback",{"metrics":{"coverage":{"digitCount":10,"hanCount":30290,"hasDigits":true,"hasHan":true,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"lang":"zh-Hans"}},{"familyAttributes":{"lang":"zh-Hant,zh-Bopo"}},{"familyAttributes":{"lang":"ja"}},{"familyAttributes":{"lang":"ko"}}]},null,null]
["/system/fonts/NotoSansCanadianAboriginal-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Cans"}}]},null,null]
["/system/fonts/NotoSansCarian-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Cari"}}]},null,null]
["/system/fonts/NotoSansChakma-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Cakm"}}]},null,null]
["/system/fonts/NotoSansCham-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Cham"}}]},null,null]
["/system/fonts/NotoSansCham-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Cham"}}]},null,null]
["/system/fonts/NotoSansCherokee-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Cher"}}]},null,null]
["/system/fonts/NotoSansCoptic-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Copt"}}]},null,null]
["/system/fonts/NotoSansCuneiform-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Xsux"}}]},null,null]
["/system/fonts/NotoSansCypriot-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Cprt"}}]},null,null]
["/system/fonts/NotoSansDeseret-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Dsrt"}}]},null,null]
["/system/fonts/NotoSansDevanagari-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Deva","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansDevanagariUI-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Deva","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansEgyptianHieroglyphs-Regular.ttf","symbol-icon",{"xmlRefs":[{"familyAttributes":{"lang":"und-Egyp"}}]},null,null]
["/system/fonts/NotoSansElbasan-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Elba"}}]},null,null]
["/system/fonts/NotoSansEthiopic-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Ethi"}}]},null,null]
["/system/fonts/NotoSansGeorgian-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Geor,und-Geok"}}]},null,null]
["/system/fonts/NotoSansGlagolitic-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Glag"}}]},null,null]
["/system/fonts/NotoSansGothic-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Goth"}}]},null,null]
["/system/fonts/NotoSansGrantha-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Gran"}}]},null,null]
["/system/fonts/NotoSansGujarati-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Gujr","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansGujarati-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Gujr","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansGujaratiUI-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Gujr","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansGujaratiUI-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Gujr","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansGunjalaGondi-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Gong"}}]},null,null]
["/system/fonts/NotoSansGurmukhi-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Guru","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansGurmukhiUI-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Guru","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansHanifiRohingya-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Rohg"}}]},null,null]
["/system/fonts/NotoSansHanunoo-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Hano"}}]},null,null]
["/system/fonts/NotoSansHatran-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Hatr"}}]},null,null]
["/system/fonts/NotoSansHebrew-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Hebr"}}]},null,null]
["/system/fonts/NotoSansHebrew-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Hebr"}}]},null,null]
["/system/fonts/NotoSansImperialAramaic-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Armi"}}]},null,null]
["/system/fonts/NotoSansInscriptionalPahlavi-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Phli"}}]},null,null]
["/system/fonts/NotoSansInscriptionalParthian-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Prti"}}]},null,null]
["/system/fonts/NotoSansJavanese-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Java"}}]},null,null]
["/system/fonts/NotoSansKaithi-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Kthi"}}]},null,null]
["/system/fonts/NotoSansKannada-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Knda","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansKannadaUI-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Knda","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansKayahLi-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Kali"}}]},null,null]
["/system/fonts/NotoSansKharoshthi-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Khar"}}]},null,null]
["/system/fonts/NotoSansKhmer-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Khmr","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansKhmerUI-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Khmr","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansKhmerUI-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Khmr","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansKhojki-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Khoj"}}]},null,null]
["/system/fonts/NotoSansLao-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Laoo","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansLao-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Laoo","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansLaoUI-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Laoo","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansLaoUI-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Laoo","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansLepcha-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Lepc"}}]},null,null]
["/system/fonts/NotoSansLimbu-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Limb"}}]},null,null]
["/system/fonts/NotoSansLinearA-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Lina"}}]},null,null]
["/system/fonts/NotoSansLinearB-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Linb"}}]},null,null]
["/system/fonts/NotoSansLisu-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Lisu"}}]},null,null]
["/system/fonts/NotoSansLycian-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Lyci"}}]},null,null]
["/system/fonts/NotoSansLydian-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Lydi"}}]},null,null]
["/system/fonts/NotoSansMalayalam-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mlym","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansMalayalamUI-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mlym","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansMandaic-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mand"}}]},null,null]
["/system/fonts/NotoSansManichaean-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mani"}}]},null,null]
["/system/fonts/NotoSansMarchen-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Marc"}}]},null,null]
["/system/fonts/NotoSansMasaramGondi-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Gonm"}}]},null,null]
["/system/fonts/NotoSansMedefaidrin-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Medf"}}]},null,null]
["/system/fonts/NotoSansMeeteiMayek-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mtei"}}]},null,null]
["/system/fonts/NotoSansMeroitic-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Merc"}}]},null,null]
["/system/fonts/NotoSansMiao-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Plrd"}}]},null,null]
["/system/fonts/NotoSansModi-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Modi"}}]},null,null]
["/system/fonts/NotoSansMongolian-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mong"}}]},null,null]
["/system/fonts/NotoSansMro-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mroo"}}]},null,null]
["/system/fonts/NotoSansMultani-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mult"}}]},null,null]
["/system/fonts/NotoSansMyanmar-Bold.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mymr","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansMyanmar-Medium.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mymr","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansMyanmar-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mymr","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansMyanmarUI-Bold.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mymr","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansMyanmarUI-Medium.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mymr","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansMyanmarUI-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mymr","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansNKo-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Nkoo"}}]},null,null]
["/system/fonts/NotoSansNabataean-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Nbat"}}]},null,null]
["/system/fonts/NotoSansNewTaiLue-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Talu"}}]},null,null]
["/system/fonts/NotoSansNewa-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Newa"}}]},null,null]
["/system/fonts/NotoSansOgham-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Ogam"}}]},null,null]
["/system/fonts/NotoSansOlChiki-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Olck"}}]},null,null]
["/system/fonts/NotoSansOldItalic-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Ital"}}]},null,null]
["/system/fonts/NotoSansOldNorthArabian-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Narb"}}]},null,null]
["/system/fonts/NotoSansOldPermic-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Perm"}}]},null,null]
["/system/fonts/NotoSansOldPersian-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Xpeo"}}]},null,null]
["/system/fonts/NotoSansOldSouthArabian-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Sarb"}}]},null,null]
["/system/fonts/NotoSansOldTurkic-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Orkh"}}]},null,null]
["/system/fonts/NotoSansOriya-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Orya","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansOriya-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Orya","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansOriyaUI-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Orya","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansOriyaUI-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Orya","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansOsage-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Osge"}}]},null,null]
["/system/fonts/NotoSansOsmanya-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Osma"}}]},null,null]
["/system/fonts/NotoSansPahawhHmong-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Hmng"}}]},null,null]
["/system/fonts/NotoSansPalmyrene-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Palm"}}]},null,null]
["/system/fonts/NotoSansPauCinHau-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Pauc"}}]},null,null]
["/system/fonts/NotoSansPhagsPa-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Phag"}}]},null,null]
["/system/fonts/NotoSansPhoenician-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Phnx"}}]},null,null]
["/system/fonts/NotoSansRejang-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Rjng"}}]},null,null]
["/system/fonts/NotoSansRunic-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Runr"}}]},null,null]
["/system/fonts/NotoSansSamaritan-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Samr"}}]},null,null]
["/system/fonts/NotoSansSaurashtra-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Saur"}}]},null,null]
["/system/fonts/NotoSansSharada-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Shrd"}}]},null,null]
["/system/fonts/NotoSansShavian-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Shaw"}}]},null,null]
["/system/fonts/NotoSansSinhala-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Sinh","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansSinhalaUI-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Sinh","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansSoraSompeng-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Sora"}}]},null,null]
["/system/fonts/NotoSansSoyombo-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Soyo"}}]},null,null]
["/system/fonts/NotoSansSundanese-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Sund"}}]},null,null]
["/system/fonts/NotoSansSylotiNagri-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Sylo"}}]},null,null]
["/system/fonts/NotoSansSymbols-Regular-Subsetted.ttf","symbol-icon",{},null,null]
["/system/fonts/NotoSansSymbols-Regular-Subsetted2.ttf","symbol-icon",{"xmlRefs":[{"familyAttributes":{"lang":"und-Zsym"}}]},null,null]
["/system/fonts/NotoSansSyriacEastern-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Syrn"}}]},null,null]
["/system/fonts/NotoSansSyriacEstrangela-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Syre"}}]},null,null]
["/system/fonts/NotoSansSyriacWestern-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Syrj"}}]},null,null]
["/system/fonts/NotoSansTagalog-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Tglg"}}]},null,null]
["/system/fonts/NotoSansTagbanwa-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Tagb"}}]},null,null]
["/system/fonts/NotoSansTaiLe-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Tale"}}]},null,null]
["/system/fonts/NotoSansTaiTham-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Lana"}}]},null,null]
["/system/fonts/NotoSansTaiViet-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Tavt"}}]},null,null]
["/system/fonts/NotoSansTakri-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Takr"}}]},null,null]
["/system/fonts/NotoSansTamil-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Taml","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansTamilUI-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Taml","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansTelugu-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Telu","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansTeluguUI-VF.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Telu","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansThaana-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Thaa"}}]},null,null]
["/system/fonts/NotoSansThaana-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Thaa"}}]},null,null]
["/system/fonts/NotoSansThai-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Thai","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansThai-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Thai","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSansThaiUI-Bold.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Thai","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansThaiUI-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Thai","variant":"compact"}}]},null,null]
["/system/fonts/NotoSansTifinagh-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Tfng"}}]},null,null]
["/system/fonts/NotoSansUgaritic-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Ugar"}}]},null,null]
["/system/fonts/NotoSansVai-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Vaii"}}]},null,null]
["/system/fonts/NotoSansWancho-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Wcho"}}]},null,null]
["/system/fonts/NotoSansWarangCiti-Regular.otf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Wara"}}]},null,null]
["/system/fonts/NotoSansYi-Regular.ttf","special-fallback",{"xmlRefs":[{"familyAttributes":{"lang":"und-Yiii"}}]},null,null]
["/system/fonts/NotoSerif-Bold.ttf","special-fallback",{"families":["ITC Stone Serif","baskerville","fantasy","georgia","goudy","palatino","serif","serif-bold","times","times new roman"],"xmlRefs":[{"familyAttributes":{"name":"serif"}}]},{"path":"/system/fonts/NotoSerif-Bold.ttf","role":"special-fallback","mode":"partial-stock","asciiLettersReplaced":52,"asciiDigitsReplaced":10},null]
["/system/fonts/NotoSerif-BoldItalic.ttf","special-fallback",{"families":["ITC Stone Serif","baskerville","fantasy","georgia","goudy","palatino","serif","serif-bold","times","times new roman"],"xmlRefs":[{"familyAttributes":{"name":"serif"}}]},{"path":"/system/fonts/NotoSerif-BoldItalic.ttf","role":"special-fallback","mode":"partial-stock","asciiLettersReplaced":52,"asciiDigitsReplaced":10},null]
["/system/fonts/NotoSerif-Italic.ttf","special-fallback",{"families":["ITC Stone Serif","baskerville","fantasy","georgia","goudy","palatino","serif","serif-bold","times","times new roman"],"xmlRefs":[{"familyAttributes":{"name":"serif"}}]},{"path":"/system/fonts/NotoSerif-Italic.ttf","role":"special-fallback","mode":"partial-stock","asciiLettersReplaced":52,"asciiDigitsReplaced":10},null]
["/system/fonts/NotoSerif-Regular.ttf","special-fallback",{"families":["ITC Stone Serif","baskerville","fantasy","georgia","goudy","palatino","serif","serif-bold","times","times new roman"],"xmlRefs":[{"familyAttributes":{"name":"serif"}}]},{"path":"/system/fonts/NotoSerif-Regular.ttf","role":"special-fallback","mode":"partial-stock","asciiLettersReplaced":52,"asciiDigitsReplaced":10},null]
["/system/fonts/NotoSerifArmenian-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Armn"}}]},null,null]
["/system/fonts/NotoSerifBengali-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Beng","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifCJK-Regular.ttc","serif",{"xmlRefs":[{"familyAttributes":{"lang":"zh-Hans"}},{"familyAttributes":{"lang":"zh-Hant,zh-Bopo"}},{"familyAttributes":{"lang":"ja"}},{"familyAttributes":{"lang":"ko"}}]},null,null]
["/system/fonts/NotoSerifDevanagari-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Deva","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifDogra-Regular.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Dogr"}}]},null,null]
["/system/fonts/NotoSerifEthiopic-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Ethi"}}]},null,null]
["/system/fonts/NotoSerifGeorgian-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Geor,und-Geok"}}]},null,null]
["/system/fonts/NotoSerifGujarati-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Gujr","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifGurmukhi-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Guru","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifHebrew-Bold.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Hebr"}}]},null,null]
["/system/fonts/NotoSerifHebrew-Regular.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Hebr"}}]},null,null]
["/system/fonts/NotoSerifHentaigana.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"ja"}}]},null,null]
["/system/fonts/NotoSerifKannada-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Knda","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifKhmer-Bold.otf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Khmr","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifKhmer-Regular.otf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Khmr","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifLao-Bold.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Laoo","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifLao-Regular.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Laoo","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifMalayalam-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mlym","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifMyanmar-Bold.otf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mymr","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifMyanmar-Regular.otf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Mymr","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifNyiakengPuachueHmong-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Hmnp"}}]},null,null]
["/system/fonts/NotoSerifSinhala-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Sinh","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifTamil-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Taml","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifTelugu-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Telu","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifThai-Bold.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Thai","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifThai-Regular.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Thai","variant":"elegant"}}]},null,null]
["/system/fonts/NotoSerifTibetan-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Tibt"}}]},null,null]
["/system/fonts/NotoSerifYezidi-VF.ttf","serif",{"xmlRefs":[{"familyAttributes":{"lang":"und-Yezi"}}]},null,null]
["/system/fonts/Roboto-Regular.ttf","ui-sans",{"families":["sans-serif-condensed","sans-serif-condensed-light","sans-serif-condensed-medium"],"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"sans-serif-condensed"}}]},{"path":"/system/fonts/Roboto-Regular.ttf","role":"ui-sans"},null]
["/system/fonts/RobotoFlex-Regular.ttf","ui-sans",{"families":["roboto-flex"],"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"roboto-flex"}}]},{"path":"/system/fonts/RobotoFlex-Regular.ttf","role":"ui-sans"},null]
["/system/fonts/RobotoStatic-Regular.ttf","latin",{"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}}},{"path":"/system/fonts/RobotoStatic-Regular.ttf","role":"latin"},null]
["/system/fonts/SourceSansPro-Bold.ttf","ui-sans",{"families":["source-sans-pro","source-sans-pro-semi-bold"],"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"source-sans-pro"}}]},{"path":"/system/fonts/SourceSansPro-Bold.ttf","role":"ui-sans"},null]
["/system/fonts/SourceSansPro-BoldItalic.ttf","ui-sans",{"families":["source-sans-pro","source-sans-pro-semi-bold"],"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"source-sans-pro"}}]},{"path":"/system/fonts/SourceSansPro-BoldItalic.ttf","role":"ui-sans"},null]
["/system/fonts/SourceSansPro-Italic.ttf","ui-sans",{"families":["source-sans-pro","source-sans-pro-semi-bold"],"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"source-sans-pro"}}]},{"path":"/system/fonts/SourceSansPro-Italic.ttf","role":"ui-sans"},null]
["/system/fonts/SourceSansPro-Regular.ttf","ui-sans",{"families":["source-sans-pro","source-sans-pro-semi-bold"],"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"source-sans-pro"}}]},{"path":"/system/fonts/SourceSansPro-Regular.ttf","role":"ui-sans"},null]
["/system/fonts/SourceSansPro-SemiBold.ttf","ui-sans",{"families":["source-sans-pro","source-sans-pro-semi-bold"],"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"source-sans-pro"}}]},{"path":"/system/fonts/SourceSansPro-SemiBold.ttf","role":"ui-sans"},null]
["/system/fonts/SourceSansPro-SemiBoldItalic.ttf","ui-sans",{"families":["source-sans-pro","source-sans-pro-semi-bold"],"metrics":{"coverage":{"digitCount":10,"hanCount":0,"hasDigits":true,"hasHan":false,"hasLatin":true,"latinCount":52}},"xmlRefs":[{"familyAttributes":{"name":"source-sans-pro"}}]},{"path":"/system/fonts/SourceSansPro-SemiBoldItalic.ttf","role":"ui-sans"},null]
'''


def topology(slots: dict) -> dict:
    return {"schema": "device-font-topology-v1", "state": "ready", "slots": slots}


def item(report: dict, path: str) -> dict:
    return next(entry for entry in report["paths"] if entry["path"] == path)


def coverage(letters=52, digits=10, han=0) -> dict:
    return {"metrics": {"coverage": {"latinCount": letters, "digitCount": digits, "hanCount": han}}}


def test_real_device_complete_accounting() -> None:
    rows = [json.loads(line) for line in DEVICE_ROWS.splitlines() if line.strip()]
    slots = {path: slot for path, _role, slot, _action, _kept in rows}
    original_roles = {path: role for path, role, _slot, _action, _kept in rows}
    replaced = [action for _path, _role, _slot, action, _kept in rows if action]
    kept = {path: reason for path, _role, _slot, _action, reason in rows if reason}
    device = topology(slots)
    roles, _ = font_role_shadow.build(device)
    # Retain the originally captured roles in the fixture. Revision 6 fixes
    # the old substring matcher reading Gothi(cOn)e as "icon" and treats the
    # two hieroglyph script fallbacks by their explicit XML language. Assert
    # exactly those intended changes, rather than silently rewriting history.
    expected_roles = dict(original_roles)
    expected_roles.update({
        "/product/fonts/DelaGothicOne-HZ.otf": "unknown-protected",
        "/product/fonts/DelaGothicOne.otf": "unknown-protected",
        "/system/fonts/NotoSansAnatolianHieroglyphs-Regular.otf": "special-fallback",
        "/system/fonts/NotoSansEgyptianHieroglyphs-Regular.ttf": "special-fallback",
    })
    assert {path: entry["role"] for path, entry in roles["slots"].items()} == expected_roles
    original = copy.deepcopy((device, roles, replaced, kept))
    report = audit.build_audit(device, roles, replaced, kept)
    assert (device, roles, replaced, kept) == original
    assert report["scope"] == "system-font-topology"
    assert report["appRendering"] == "not-assessed"
    assert report["auditedPathCount"] == report["topologyPathCount"] == 288
    assert len({entry["path"] for entry in report["paths"]}) == 288
    assert {entry["path"] for entry in report["paths"]} == set(slots)
    assert sum(report["statusCounts"].values()) == 288
    assert report["statusCounts"] == {
        "full-replaced": 49, "partial-replaced": 7, "kept-text": 225,
        "protected-nontext": 4, "unmeasured": 3,
    }
    assert report["replacedPathCount"] == report["replacementRecordCount"] == 56
    assert report["beforeMeasurementCounts"] == {"measured": 51, "partial": 0, "unknown": 237}
    # Old report's 56 outputs contain proof for seven partial replacements,
    # not proof that the other 49 outputs had complete English/digit sources.
    assert report["replacedAsciiCounts"] == {"complete": 7, "incomplete": 0, "unknown": 49}
    assert report["sourceMeasurementCounts"] == {"measured": 0, "partial": 0, "unknown": 288}
    assert report["integrityIssues"] == []
    assert {entry["path"]: entry["role"] for entry in report["paths"]} == expected_roles
    for path, reason in kept.items():
        assert item(report, path)["reason"] == reason
    assert item(report, "/system/fonts/DancingScript-Regular.ttf")["reason"] == \
        "partial-stock-variable-unsupported"
    assert item(report, "/system/fonts/MiSansVF_Overlay.ttf")["status"] == "unmeasured"
    for entry in report["paths"]:
        if entry["beforeCoverage"]["measurement"] == "unknown":
            assert entry["beforeCoverage"]["asciiLetters"] is None
            assert entry["beforeCoverage"]["asciiDigits"] is None


def test_proof_and_shared_ascii_boundary() -> None:
    slots = {
        "/system/fonts/Roboto-Regular.ttf": {"families": ["sans-serif"], **coverage()},
        "/system/fonts/SourceSansPro-Regular.ttf": coverage(),
        "/system/fonts/NotoSerif-Regular.ttf": {"families": ["serif"], **coverage()},
        "/system/fonts/DroidSansMono.ttf": {"families": ["monospace"], **coverage()},
        "/system/fonts/ComingSoon.ttf": {"families": ["casual"], **coverage()},
    }
    device = topology(slots)
    roles, _ = font_role_shadow.build(device)
    replacements = [
        {"path": "/system/fonts/Roboto-Regular.ttf", "sourceCoverage": {"asciiLetters": 52, "asciiDigits": 10}},
        {"path": "/system/fonts/SourceSansPro-Regular.ttf", "sourceCoverage": {"asciiLetters": 51, "asciiDigits": 10}},
        {"path": "/system/fonts/NotoSerif-Regular.ttf", "mode": "partial-stock",
         "asciiLettersReplaced": 51, "asciiDigitsReplaced": 10,
         "sourceCoverage": {"asciiLetters": 52, "asciiDigits": 10},
         "protectedSharedGlyphs": ["A"], "protectedMetricGlyphs": ["f"],
         "advancePolicy": "retain-stock-cell"},
        {"path": "/system/fonts/DroidSansMono.ttf", "mode": "partial-stock",
         "latinGlyphsReplaced": 112, "digitGlyphsReplaced": 10},
        {"path": "/system/fonts/ComingSoon.ttf", "mode": "partial-stock",
         "asciiLettersReplaced": 52, "asciiDigitsReplaced": 10},
    ]
    report = audit.build_audit(device, roles, replacements, {})
    assert report["replacedAsciiCounts"] == {"complete": 2, "incomplete": 2, "unknown": 1}
    assert item(report, "/system/fonts/Roboto-Regular.ttf")["asciiComplete"] is True
    assert item(report, "/system/fonts/SourceSansPro-Regular.ttf")["asciiComplete"] is False
    shared = item(report, "/system/fonts/NotoSerif-Regular.ttf")
    assert shared["asciiComplete"] is False
    assert shared["sourceCoverage"]["asciiLetters"] == 52
    assert shared["replacementCoverage"]["asciiLetters"] == 51
    assert shared["partialBoundary"] == {"protectedSharedGlyphs": ["A"], "protectedMetricGlyphs": ["f"],
                                          "advancePolicy": "retain-stock-cell"}
    # A total of 112 Latin glyphs says nothing about all 52 ASCII codepoints.
    assert item(report, "/system/fonts/DroidSansMono.ttf")["asciiComplete"] is None
    assert item(report, "/system/fonts/ComingSoon.ttf")["asciiComplete"] is True


def test_missing_measurements_and_untouched_reasons() -> None:
    slots = {
        "/system/fonts/NotoSansCJK.ttc": {"families": ["sans-serif"], "metrics": {"coverage": {"hasLatin": True}}},
        "/system/fonts/DancingScript-Regular.ttf": {"families": ["cursive"]},
        "/system/fonts/Other.ttf": {"metrics": {"coverage": {"latinCount": 52}}},
        "/system/fonts/Unreadable.ttf": {},
        "/system/fonts/Zero.ttf": coverage(0, 0),
        "/system/fonts/InvalidCounts.ttf": coverage(True, 11),
        "/system/fonts/NotoColorEmoji.ttf": {},
        "/system/fonts/MaterialIcons.ttf": {},
        "/data/fonts/files/Downloaded.ttf": {"families": ["sans-serif"], **coverage()},
    }
    device = topology(slots)
    roles, _ = font_role_shadow.build(device)
    kept = {"/system/fonts/NotoSansCJK.ttc": "partial-stock-collection-unsupported",
            "/system/fonts/DancingScript-Regular.ttf": "partial-stock-variable-unsupported",
            "/system/fonts/Unreadable.ttf": "stock-metrics-missing"}
    report = audit.build_audit(device, roles, [], kept)
    assert report["beforeMeasurementCounts"] == {"measured": 2, "partial": 1, "unknown": 6}
    for path, reason in kept.items():
        assert item(report, path)["reason"] == reason
    assert item(report, "/system/fonts/Other.ttf")["beforeCoverage"] == \
        {"measurement": "partial", "asciiLetters": 52, "asciiDigits": None}
    assert item(report, "/system/fonts/Zero.ttf")["beforeCoverage"] == \
        {"measurement": "measured", "asciiLetters": 0, "asciiDigits": 0}
    assert item(report, "/system/fonts/InvalidCounts.ttf")["beforeCoverage"]["measurement"] == "unknown"
    for path in ("/system/fonts/NotoColorEmoji.ttf", "/system/fonts/MaterialIcons.ttf",
                 "/data/fonts/files/Downloaded.ttf"):
        assert item(report, path)["status"] == "protected-nontext"
        assert item(report, path)["asciiComplete"] is None
    assert item(report, "/data/fonts/files/Downloaded.ttf")["protectionReason"] == "dynamic-font"
    assert report["replacedPathCount"] == 0


def test_digit_only_present_ascii_and_missing_before() -> None:
    # Most script-specific Android fallbacks contain only ASCII digits. They
    # must not be reported as retaining 52 letters they never contained.
    slots = {
        "/system/fonts/NotoSansArabic.ttf": {},
        "/system/fonts/NotoSansTibetan.ttf": coverage(0, 10),
        "/system/fonts/UnreadableOriginal.ttf": {},
        "/system/fonts/SharedLatin.ttf": {},
        "/system/fonts/PartialStockLatin.ttf": coverage(26, 10),
    }
    device = topology(slots)
    roles, _ = font_role_shadow.build(device)
    replacements = [
        {"path": "/system/fonts/NotoSansArabic.ttf", "mode": "partial-stock",
         "asciiLettersBefore": 0, "asciiDigitsBefore": 10,
         "asciiLettersReplaced": 0, "asciiDigitsReplaced": 10},
        {"path": "/system/fonts/NotoSansTibetan.ttf", "mode": "partial-stock",
         "asciiLettersReplaced": 0, "asciiDigitsReplaced": 9},
        {"path": "/system/fonts/UnreadableOriginal.ttf", "mode": "partial-stock",
         "asciiLettersReplaced": 52, "asciiDigitsReplaced": 10},
        {"path": "/system/fonts/SharedLatin.ttf", "mode": "partial-stock",
         "asciiLettersBefore": 52, "asciiDigitsBefore": 10,
         "asciiLettersReplaced": 51, "asciiDigitsReplaced": 10},
        {"path": "/system/fonts/PartialStockLatin.ttf",
         "sourceCoverage": {"asciiLetters": 51, "asciiDigits": 10}},
    ]
    report = audit.build_audit(device, roles, replacements, {})
    digits = item(report, "/system/fonts/NotoSansArabic.ttf")
    assert digits["asciiComplete"] is False  # Preserve strict 52 + 10 semantics.
    assert digits["originalAsciiComplete"] is False
    assert digits["presentAsciiComplete"] is True
    assert digits["retainedPresentAscii"] == {"letters": 0, "digits": 0}
    assert digits["beforeCoverage"] == {"measurement": "measured", "asciiLetters": 0, "asciiDigits": 10}
    retained = item(report, "/system/fonts/NotoSansTibetan.ttf")
    assert retained["presentAsciiComplete"] is False
    assert retained["retainedPresentAscii"] == {"letters": 0, "digits": 1}
    unmeasured = item(report, "/system/fonts/UnreadableOriginal.ttf")
    assert unmeasured["asciiComplete"] is True
    assert unmeasured["originalAsciiComplete"] is None
    assert unmeasured["presentAsciiComplete"] is None
    assert unmeasured["retainedPresentAscii"] == {"letters": None, "digits": None}
    shared = item(report, "/system/fonts/SharedLatin.ttf")
    assert shared["originalAsciiComplete"] is True
    assert shared["presentAsciiComplete"] is False
    assert shared["retainedPresentAscii"] == {"letters": 1, "digits": 0}
    # Full source 51 does not prove the intersection with a 26-letter stock.
    # For example the source could omit A, while A was one of stock's 26.
    intersection = item(report, "/system/fonts/PartialStockLatin.ttf")
    assert intersection["presentAsciiComplete"] is None
    assert intersection["retainedPresentAscii"] == {"letters": None, "digits": 0}
    assert report["beforeMeasurementCounts"] == {"measured": 4, "partial": 0, "unknown": 1}


def test_identity_conflicts_and_invalid_proofs() -> None:
    slots = {"/system/fonts/A.ttf": coverage(), "/system/fonts/NotoColorEmoji.ttf": {},
             "/system/fonts/Invalid.ttf": None}
    device = topology(slots)
    roles, _ = font_role_shadow.build(device)
    records = [{"path": "/system/fonts/A.ttf", "sourceCoverage": {"asciiLetters": 52, "asciiDigits": 10}},
               {"path": "/system/fonts/A.ttf", "sourceCoverage": {"asciiLetters": True, "asciiDigits": 11},
                "asciiComplete": True},
               {"path": "/system/fonts/NotoColorEmoji.ttf"},
               {"path": "/system/fonts/Outside.ttf"}, None]
    kept = {"/system/fonts/A.ttf": "kept-conflict", "/system/fonts/Outside.ttf": "outside"}
    report = audit.build_audit(device, roles, records, kept)
    assert report["replacementRecordCount"] == 5 and report["replacedPathCount"] == 2
    assert report["topologyPathCount"] == report["auditedPathCount"] == 3
    assert sum(report["statusCounts"].values()) == 3
    assert report["replacementPathsOutsideTopology"] == ["/system/fonts/Outside.ttf"]
    assert report["keptPathsOutsideTopology"] == ["/system/fonts/Outside.ttf"]
    assert {issue["kind"] for issue in report["integrityIssues"]} == {
        "duplicate-replacement-path", "invalid-replacement-record", "replacement-and-kept-conflict",
        "protected-path-replaced", "invalid-topology-slot",
    }
    assert item(report, "/system/fonts/A.ttf")["asciiComplete"] is None
    assert item(report, "/system/fonts/Invalid.ttf")["reason"] == "invalid-topology-slot"
    json.dumps(report)  # Every unknown must remain a JSON null, not an invalid number.


def main() -> int:
    test_real_device_complete_accounting()
    test_proof_and_shared_ascii_boundary()
    test_missing_measurements_and_untouched_reasons()
    test_digit_only_present_ascii_and_missing_before()
    test_identity_conflicts_and_invalid_proofs()
    print("luoshu_coverage_audit_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
