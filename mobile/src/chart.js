import React, { useState } from 'react';
import { Text, View } from 'react-native';
import Svg, { G, Line, Rect, Text as SvgText } from 'react-native-svg';
import { money } from './format';
import { colors } from './theme';
import { Muted, s } from './ui';

const AXIS_W = 40;
const LABEL_H = 18;

// Teto "redondo" para o eixo: 1, 2, 2,5 ou 5 x 10^n
function niceMax(v) {
  if (v <= 0) return 100;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v);
}

const short = (n) => (n >= 1000 ? `${(n / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}k` : String(Math.round(n)));

/**
 * Barras agrupadas por dia: duas séries lado a lado.
 * data: [{ key, label, a, b }]  (a = faturamento, b = gastos)
 */
export function BarChart({ data, height = 170, labels = ['Faturamento', 'Gastos'], barColors = [colors.primary, colors.accent], detail }) {
  const [width, setWidth] = useState(0);
  const [sel, setSel] = useState(null);
  const max = niceMax(Math.max(0, ...data.map((d) => Math.max(d.a, d.b))));
  const plotW = Math.max(0, width - AXIS_W);
  const plotH = height - LABEL_H;
  const slot = data.length ? plotW / data.length : 0;
  const bar = Math.max(1.5, Math.min(12, slot * 0.36));
  const y = (v) => plotH - (v / max) * (plotH - 6);
  const every = Math.max(1, Math.ceil(data.length / 8)); // no máximo ~8 rótulos no eixo X
  const picked = sel !== null ? data[sel] : null;

  return (
    <View onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
      {width ? (
        <Svg width={width} height={height}>
          {[0, 0.5, 1].map((f) => (
            <G key={f}>
              <Line x1={AXIS_W} x2={width} y1={y(max * f)} y2={y(max * f)} stroke={colors.line} strokeWidth={1} />
              <SvgText x={AXIS_W - 6} y={y(max * f) + 4} fontSize={10} fill={colors.muted} textAnchor="end">
                {short(max * f)}
              </SvgText>
            </G>
          ))}
          {data.map((d, i) => {
            const cx = AXIS_W + slot * i + slot / 2;
            const dim = sel !== null && sel !== i ? 0.35 : 1;
            return (
              <G key={d.key}>
                {sel === i ? <Rect x={cx - slot / 2} y={0} width={slot} height={plotH} fill={colors.infoBg} /> : null}
                <Rect x={cx - bar - 0.5} y={y(d.a)} width={bar} height={plotH - y(d.a)} rx={1.5} fill={barColors[0]} opacity={dim} />
                <Rect x={cx + 0.5} y={y(d.b)} width={bar} height={plotH - y(d.b)} rx={1.5} fill={barColors[1]} opacity={dim} />
                {i % every === 0 ? (
                  <SvgText x={cx} y={height - 4} fontSize={10} fill={colors.muted} textAnchor="middle">{d.label}</SvgText>
                ) : null}
                {/* área de toque do dia inteiro */}
                <Rect x={cx - slot / 2} y={0} width={slot} height={height} fill="transparent"
                      onPress={() => setSel(sel === i ? null : i)} />
              </G>
            );
          })}
        </Svg>
      ) : <View style={{ height }} />}
      <View style={[s.row, { gap: 16, marginTop: 8, flexWrap: 'wrap' }]}>
        {labels.map((l, i) => (
          <View key={l} style={[s.row, { gap: 6 }]}>
            <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: barColors[i] }} />
            <Muted>{picked ? `${l}: ${money(i ? picked.b : picked.a)}` : l}</Muted>
          </View>
        ))}
        {picked ? <Text style={[s.muted, { fontWeight: '700' }]}>{detail ? detail(picked) : picked.label}</Text> : null}
      </View>
      {!picked && data.length ? <Muted style={{ marginTop: 4, fontSize: 12 }}>Toque em um dia para ver os valores.</Muted> : null}
    </View>
  );
}
