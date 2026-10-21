import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import Svg, { Line } from 'react-native-svg';
import Ionicons from '@expo/vector-icons/Ionicons';
import { hm, phoneLabel } from '../format';
import { STATUS } from '../status';
import { SPACE, TYPE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { haptic } from '../ui';

export const HOUR_H = 76; // altura de uma hora na grade
const AXIS_W = 52;
const MIN_BLOCK = 30; // altura mínima de um bloco curto, para caber o texto e o toque

// "2026-10-08T13:30:00" -> 810 (minutos desde a meia-noite)
export const toMin = (iso) => Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16));
const pad = (n) => String(n).padStart(2, '0');
export const fromMin = (day, m) => `${day}T${pad(Math.floor(m / 60))}:${pad(m % 60)}:00`;

// Altura do toque dentro da coluna. Celular: locationY. Web: o onPress recebe um MouseEvent, sem locationY
// (antes o minuto virava NaN e todo horário vago respondia "não está livre").
export function tapY(e) {
  const n = (e && e.nativeEvent) || {};
  if (Number.isFinite(n.locationY)) return n.locationY;
  const t = e && e.currentTarget;
  if (t && typeof t.getBoundingClientRect === 'function' && Number.isFinite(n.clientY)) {
    return n.clientY - t.getBoundingClientRect().top;
  }
  if (Number.isFinite(n.offsetY)) return n.offsetY;
  return NaN;
}

// Faixa de horas da grade: expediente e agendamentos do dia, com margem; padrão 8h às 20h
export function hourRange(columns) {
  const starts = [];
  const ends = [];
  columns.forEach((col) => {
    col.working.forEach((w) => { starts.push(toMin(w.start)); ends.push(toMin(w.end)); });
    col.appointments.forEach((a) => { starts.push(toMin(a.start)); ends.push(toMin(a.end) || 24 * 60); });
  });
  if (!starts.length) return [8, 20];
  return [Math.max(0, Math.floor(Math.min(...starts) / 60)), Math.min(24, Math.ceil(Math.max(...ends) / 60))];
}

// Agendamentos que se sobrepõem lado a lado (raias)
function lanes(appts) {
  const sorted = [...appts].sort((a, b) => a.start.localeCompare(b.start));
  const out = [];
  let group = [];
  let groupEnd = '';
  const flush = () => {
    const laneEnds = [];
    const placed = group.map((a) => {
      let lane = laneEnds.findIndex((e) => e <= a.start);
      if (lane < 0) { lane = laneEnds.length; laneEnds.push(a.end); } else laneEnds[lane] = a.end;
      return { a, lane };
    });
    placed.forEach((p) => out.push({ ...p, lanes: laneEnds.length }));
    group = [];
    groupEnd = '';
  };
  sorted.forEach((a) => {
    if (group.length && a.start >= groupEnd) flush();
    group.push(a);
    if (a.end > groupEnd) groupEnd = a.end;
  });
  if (group.length) flush();
  return out;
}

// Bloqueio hachurado (linhas diagonais desenhadas no próprio SVG)
function Hatch({ width, height, color }) {
  const lines = [];
  for (let x = -height; x < width; x += 9) lines.push(x);
  return (
    <Svg width={width} height={height} style={{ position: 'absolute' }} pointerEvents="none">
      {lines.map((x) => <Line key={x} x1={x} y1={height} x2={x + height} y2={0} stroke={color} strokeWidth={1.5} />)}
    </Svg>
  );
}

// Mesma cor dos selos (status.js é a fonte única): "agendado" é info, não a cor do segmento
const TONE_OF = Object.fromEntries(Object.entries(STATUS).map(([k, x]) => [k, x.tone]));

function ApptBlock({ a, top, height, left, width, onPress, onLongPress, showPro }) {
  const { c, font } = useTheme();
  const tone = TONE_OF[a.status] || 'info';
  const bar = tone === 'accent' ? c.accentText : tone === 'neutral' ? c.border : c.status[tone];
  const bg = tone === 'accent' ? c.accentSoft : tone === 'neutral' ? c.neutralBg : c.statusBg[tone];
  const fg = tone === 'neutral' ? c.textMuted : c.text;
  const small = height < 48;
  const name = a.customer_name || phoneLabel(a.customer_phone);
  return (
    <Pressable onPress={() => onPress(a)} onLongPress={() => { haptic.tap(); onLongPress(a); }} delayLongPress={350}
               accessibilityRole="button"
               // começa pelo texto visível (WCAG 2.5.3) e completa com o que não coube no bloco
               accessibilityLabel={`${hm(a.start)} ${name}${small ? '' : `, ${a.service_name}${showPro ? ` · ${a.barber_name}` : ''}`}`
                 + `, até ${hm(a.end)}${small ? `, ${a.service_name}` : ''}${showPro && !small ? '' : `, ${a.barber_name}`}`}
               accessibilityHint="Toque e segure para ações rápidas"
               style={({ pressed }) => ({
                 position: 'absolute', top, left, width, height, borderRadius: 8, backgroundColor: c.surface,
                 overflow: 'hidden', opacity: pressed ? 0.8 : 1, borderWidth: 1,
                 borderColor: a.status === 'pending_approval' ? c.accentText : c.divider,
                 borderStyle: a.status === 'pending_approval' ? 'dashed' : 'solid',
               })}>
      <View style={{ flex: 1, flexDirection: 'row', backgroundColor: bg }}>
        <View style={{ width: 4, backgroundColor: bar }} />
        <View style={{ flex: 1, paddingHorizontal: 6, paddingVertical: small ? 2 : 4 }}>
          <Text numberOfLines={1} maxFontSizeMultiplier={1.2}
                style={{ fontFamily: font.bold, fontSize: small ? TYPE.caption : 14, color: fg }}>
            {hm(a.start)} {name}{' '/* separa da linha de baixo no nome lido (WCAG 2.5.3) */}
          </Text>
          {!small ? (
            <Text numberOfLines={height > 64 ? 2 : 1} maxFontSizeMultiplier={1.2}
                  style={{ fontFamily: font.medium, fontSize: TYPE.caption, color: c.textMuted }}>
              {a.service_name}{showPro ? ` · ${a.barber_name}` : ''}
            </Text>
          ) : null}
        </View>
        {a.payment_status === 'pending' ? (
          <Ionicons name="cash-outline" size={14} color={c.statusText.warning} style={{ margin: 4 }} />
        ) : null}
      </View>
    </Pressable>
  );
}

function Column({ col, day, width, start, end, onEmpty, onAppt, onApptLong, showPro }) {
  const { c, font } = useTheme();
  const y = (m) => ((m - start * 60) * HOUR_H) / 60;
  const height = (end - start) * HOUR_H;
  const placed = useMemo(() => lanes(col.appointments), [col.appointments]);
  return (
    <View style={{ width, height, backgroundColor: c.neutralBg, borderLeftWidth: 1, borderLeftColor: c.divider }}>
      {/* expediente em cor de superfície; fora dele fica o fundo mais apagado */}
      {col.working.map((w) => (
        <View key={w.start} pointerEvents="none" style={{
          position: 'absolute', left: 0, right: 0, top: y(toMin(w.start)),
          height: y(toMin(w.end)) - y(toMin(w.start)), backgroundColor: c.surface,
        }} />
      ))}
      {Array.from({ length: end - start }, (_, i) => (
        <View key={i} pointerEvents="none" style={{
          position: 'absolute', left: 0, right: 0, top: i * HOUR_H, height: 1, backgroundColor: c.divider,
        }} />
      ))}
      {/* toque num horário vago */}
      <Pressable style={{ position: 'absolute', top: 0, bottom: 0, left: 0, right: 0 }} accessibilityRole="button"
                 accessibilityLabel={`Horários de ${col.name}. Toque num horário vago para agendar`}
                 onPress={(e) => {
                   const py = tapY(e);
                   if (Number.isFinite(py)) onEmpty(col, start * 60 + Math.floor((py * 60) / HOUR_H));
                 }} />
      {col.blocks.map((k) => {
        const top = y(Math.max(start * 60, k.start.slice(0, 10) < day ? 0 : toMin(k.start)));
        const bottom = y(Math.min(end * 60, k.end.slice(0, 10) > day ? 24 * 60 : toMin(k.end)));
        return (
          <View key={k.id} pointerEvents="none" accessibilityLabel={`Bloqueado: ${k.reason || 'sem motivo'}`}
                style={{ position: 'absolute', left: 0, right: 0, top, height: Math.max(2, bottom - top), overflow: 'hidden',
                         backgroundColor: c.background }}>
            <Hatch width={width} height={Math.max(2, bottom - top)} color={c.divider} />
            <Text numberOfLines={1} style={{ margin: 4, fontFamily: font.medium, fontSize: TYPE.caption, color: c.textMuted }} maxFontSizeMultiplier={1.2}>
              {k.reason || 'Bloqueado'}
            </Text>
          </View>
        );
      })}
      {placed.map(({ a, lane, lanes: n }) => {
        const top = y(toMin(a.start));
        const h = Math.max(MIN_BLOCK, y(toMin(a.end) || 24 * 60) - top - 2);
        const w = (width - 6) / n;
        return (
          <ApptBlock key={a.id} a={a} top={top + 1} height={h} left={3 + lane * w} width={w - 2}
                     onPress={onAppt} onLongPress={onApptLong} showPro={showPro} />
        );
      })}
    </View>
  );
}

/**
 * Grade de um dia com eixo de horas. columns: [{ key, id, name, working, blocks, appointments, free }]
 * Uma coluna = Timeline; várias = Profissionais lado a lado (rola na horizontal se não couber).
 */
export function DayGrid({ day, columns, now, onEmpty, onAppt, onApptLong, showPro, header = true }) {
  const { c, s, font } = useTheme();
  const [width, setWidth] = useState(0);
  const [start, end] = hourRange(columns);
  const scroll = useRef(null);
  const today = now && now.slice(0, 10) === day;
  const nowMin = today ? toMin(now) : null;
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!today) return undefined;
    const id = setInterval(() => setTick((t) => t + 1), 60000); // move a linha do agora
    return () => clearInterval(id);
  }, [today]);
  const liveNow = today ? nowMin + tick : null;
  const colW = columns.length === 1 ? Math.max(0, width - AXIS_W) : Math.max(150, (width - AXIS_W) / columns.length);
  const height = (end - start) * HOUR_H;

  // Abre já no horário atual (ou no começo do expediente)
  useEffect(() => {
    if (!width || !scroll.current) return;
    const target = liveNow !== null ? ((liveNow - start * 60) * HOUR_H) / 60 - HOUR_H : 0;
    scroll.current.scrollTo({ y: Math.max(0, target), animated: false });
  }, [width, day]); // eslint-disable-line react-hooks/exhaustive-deps

  const body = (
    <View>
      {header && columns.length > 1 ? (
        <View style={{ flexDirection: 'row', height: 40 }}>
          {columns.map((col) => (
            <View key={col.key} style={{ width: colW, justifyContent: 'center', paddingHorizontal: SPACE(2) }}>
              <Text numberOfLines={1} style={{ fontFamily: font.bold, fontSize: 15, color: c.text }} maxFontSizeMultiplier={1.2}>
                {col.name}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
      <View style={{ flexDirection: 'row' }}>
        {columns.map((col) => (
          <Column key={col.key} col={col} day={day} width={colW} start={start} end={end}
                  onEmpty={onEmpty} onAppt={onAppt} onApptLong={onApptLong} showPro={showPro} />
        ))}
      </View>
    </View>
  );

  return (
    <View style={{ flex: 1 }} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
      {width ? (
        <ScrollView ref={scroll} contentContainerStyle={{ paddingBottom: SPACE(10) }}>
          <View style={{ flexDirection: 'row' }}>
            <View style={{ width: AXIS_W, paddingTop: header && columns.length > 1 ? 40 : 0 }}>
              {Array.from({ length: end - start + 1 }, (_, i) => (
                <Text key={i} style={[s.caption, { position: 'absolute', top: (header && columns.length > 1 ? 40 : 0) + i * HOUR_H - 8,
                                                   right: 8, fontFamily: font.semibold }]} maxFontSizeMultiplier={1.2}>
                  {pad(start + i)}:00
                </Text>
              ))}
              <View style={{ height }} />
            </View>
            {columns.length > 1 ? <ScrollView horizontal showsHorizontalScrollIndicator>{body}</ScrollView> : body}
          </View>
          {liveNow !== null && liveNow >= start * 60 && liveNow <= end * 60 ? (
            <View pointerEvents="none" accessibilityRole="image" accessibilityLabel="Agora" style={{
              position: 'absolute', left: AXIS_W - 6, right: 0,
              top: (header && columns.length > 1 ? 40 : 0) + ((liveNow - start * 60) * HOUR_H) / 60 - 1,
              flexDirection: 'row', alignItems: 'center',
            }}>
              <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: c.statusText.danger }} />
              <View style={{ flex: 1, height: 2, backgroundColor: c.statusText.danger }} />
            </View>
          ) : null}
        </ScrollView>
      ) : null}
    </View>
  );
}
