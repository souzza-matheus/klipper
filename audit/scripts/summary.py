"""Resume os JSON de audit/data em tabelas Markdown (axe, alvos de toque, textos pequenos)."""
import collections
import glob
import json
import os

D = '/home/souzza-matheus/barberbot/audit/data'
out = []

# ---------------- axe do app
for f in sorted(glob.glob(f'{D}/app-*.json')):
    d = json.load(open(f))
    name = os.path.basename(f)[:-5]
    agg = collections.defaultdict(lambda: [0, set(), ''])
    for a in d['axe']:
        for v in a['violations']:
            g = agg[(v['id'], v['impact'])]
            g[0] += v['count']
            g[1].add(a['label'])
            g[2] = v['help']
    out.append(f'\n### axe: {name} ({len(d["axe"])} telas analisadas)\n')
    out.append('| regra | impacto | ocorrências | telas | o que é |\n|---|---|---|---|---|')
    order = {'critical': 0, 'serious': 1, 'moderate': 2, 'minor': 3}
    for (rid, imp), (n, screens, h) in sorted(agg.items(), key=lambda x: (order.get(x[0][1], 9), -x[1][0])):
        out.append(f'| {rid} | {imp} | {n} | {len(screens)} | {h} |')
    if d.get('measure'):
        out.append(f'\n#### Alvos < 48 px e textos < 13 px: {name}\n')
        out.append('| tela | alvos < 48 px | exemplos | textos < 13 px (nós) | tamanhos |\n|---|---|---|---|---|')
        for scr, m in d['measure'].items():
            ex = '; '.join(f'{t["el"][:38]} {t["w"]}x{t["h"]}' for t in m['smallTargets'][:3])
            sizes = ', '.join(f'{k}: {v["count"]}' for k, v in sorted(m['smallText'].items()))
            n_text = sum(v['count'] for v in m['smallText'].values())
            out.append(f'| {scr} | {len(m["smallTargets"])} | {ex} | {n_text} | {sizes} |')

open(f'{D}/resumo-medicoes.md', 'w').write('\n'.join(out))
print('\n'.join(out)[:6000])
