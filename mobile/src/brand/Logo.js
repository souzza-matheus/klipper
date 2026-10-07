import React from 'react';
import Svg, { Defs, G, LinearGradient, Path, Stop } from 'react-native-svg';
import * as LOGO from './logoData';

// Logo SyncServ vetorial, desenhado a partir dos SVG do kit (src/brand/logoData.js). Não redesenhar: só escalar.
const TAGS = { defs: Defs, g: G, linearGradient: LinearGradient, stop: Stop, path: Path };

// color: pinta tudo o que não é "none" com uma cor só (símbolo na cor do segmento), sem o degradê
function paint(attrs, color) {
  if (!color) return attrs;
  const out = { ...attrs };
  ['fill', 'stroke'].forEach((k) => {
    if (out[k] && out[k] !== 'none') out[k] = color;
  });
  return out;
}

function render(nodes, color, prefix = 'n') {
  return nodes.map(([tag, attrs, kids], i) => {
    if (color && tag === 'defs') return null; // o degradê não é usado quando há cor
    const El = TAGS[tag];
    if (!El) return null;
    return (
      <El key={`${prefix}${i}`} {...paint(attrs, color)}>
        {kids ? render(kids, color, `${prefix}${i}-`) : null}
      </El>
    );
  });
}

function ratio(viewBox) {
  const [, , w, h] = viewBox.split(' ').map(Number);
  return w / h;
}

function Logo({ data, width, height, color, label = 'SyncServ' }) {
  const r = ratio(data.viewBox);
  const w = width ?? height * r;
  const h = height ?? width / r;
  return (
    <Svg width={w} height={h} viewBox={data.viewBox} accessibilityRole="image" accessibilityLabel={label}>
      {render(data.children, color)}
    </Svg>
  );
}

// Símbolo. Sem color: degradê azul -> verde do kit. Com color: o símbolo inteiro naquela cor.
// Exportado como Symbol (nome pedido pela marca); dentro do app importe como { Symbol as BrandSymbol }
// para não esconder o Symbol global do JavaScript.
function SyncSymbol({ size = 32, color }) {
  return <Logo data={LOGO.symbol} height={size} color={color} />;
}

// Símbolo + nome na horizontal. variant "dark" = para fundo escuro (degradê, Sync em branco); "light" = fundo claro.
export function Wordmark({ height = 32, variant = 'dark' }) {
  return <Logo data={variant === 'light' ? LOGO.horizontalLight : LOGO.horizontalDark} height={height} />;
}

// Símbolo em cima do nome (login e splash interna)
export function LogoVertical({ width = 180, variant = 'dark' }) {
  return <Logo data={variant === 'light' ? LOGO.verticalLight : LOGO.verticalDark} width={width} />;
}

export { SyncSymbol as Symbol };
