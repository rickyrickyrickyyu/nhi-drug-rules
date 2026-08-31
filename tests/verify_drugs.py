"""對照健保條文原文，逐藥驗證本站呈現是否正確。

驗法：從條文原文抓出可機械驗證的事實（劑量上限、療程天數、專科限制…），
再檢查本站的結構化欄位有沒有反映出來。條文原文是唯一真相來源。
"""
import json, pathlib, re, sys

import os
os.chdir(pathlib.Path(__file__).resolve().parents[1])
D = {i['k']: i for i in json.load(open('public/data/derm.json', encoding='utf-8'))['ing']}
R = json.load(open('data/build/rules.json', encoding='utf-8'))

def txt(code): return (R.get(code) or {}).get('text', '')

CASES = [
    # (學名, 章節, 條文中必須出現的關鍵字, 本站應標的旗標)
    ('ISOTRETINOIN',  '13.4.',      ['限皮膚科專科醫師', '同意書', '事前審查', '100 mg'], ['prior_review','consent_form','specialist_only']),
    ('PERMETHRIN',    '13.15.',     ['30gm', '7 天後', '皮膚科醫師確診'], []),
    ('TERBINAFINE',   '10.6.4.',    ['手指甲癬', '42 顆', '84 顆', '16 週'], []),
    ('CALCIPOTRIOL',  '13.3.1.',    ['尋常性牛皮癬', '30gm'], []),
    ('DUPILUMAB',     '13.17.1.',   ['EASI', '事前審查', '皮膚科'], ['prior_review','specialist_only']),
    ('ACICLOVIR',     '10.7.1.1.',  ['疱疹性腦炎', '10 天為限', '擇一使用'], ['no_combination','course_limited']),
    ('ACICLOVIR',     '10.7.1.2.',  ['3 日內', '5 公克'], []),
    ('IVERMECTIN',    '13.16.',     [], []),
    ('APREMILAST',    '8.2.16.',    ['斑塊乾癬', 'methotrexate'], []),
    ('SPESOLIMAB',    '8.2.4.6.2.', ['膿疱性乾癬'], []),
    ('ACITRETIN',     '13.5.',      [], []),
    ('TACROLIMUS',    '13.10.',     [], []),
    ('PIMECROLIMUS',  '13.11.',     [], []),
    ('CICLOSPORIN',   '8.2.1.',     ['乾癬', '異位性皮膚炎'], []),
    ('GUSELKUMAB',    '8.2.4.11.',  ['掌蹠膿皰症'], []),
    ('SECUKINUMAB',   '8.2.4.14.',  ['化膿性汗腺炎'], []),
]
fails = []
for inn, code, keywords, flags in CASES:
    it = D.get(inn)
    t = txt(code)
    probs = []
    if not it: probs.append('不在皮膚科子集')
    if not t: probs.append(f'章節 {code} 無條文')
    if it and code not in {s for r in it['r'] for s in r['s']}:
        probs.append(f'學名未連到 {code}')
    for k in keywords:
        if k not in t: probs.append(f'條文缺關鍵字「{k}」')
    if it:
        f = it['f']
        for fl in flags:
            got = f.get({'prior_review':'pa','consent_form':'cs','no_combination':'co',
                         'course_limited':'co','specialist_only':'sp'}[fl])
            if not got: probs.append(f'旗標 {fl} 未標記')
    status = '✅' if not probs else '❌'
    print(f'{status} {inn:16s} {code:12s} {"；".join(probs) if probs else "相符"}')
    if probs: fails.append((inn, code, probs))
print(f'\n{len(CASES)-len(fails)}/{len(CASES)} 通過')
sys.exit(1 if fails else 0)
