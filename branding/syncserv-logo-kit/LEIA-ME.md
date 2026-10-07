# SyncServ — kit de logo

## Cores
| Uso | Cor | Hex |
| --- | --- | --- |
| Primária (Sync, seta) | Azul Elétrico | #0284C7 |
| Secundária (Serv, balão, Pix) | Verde Conexão | #22C55E |
| Fundo escuro | Grafite Fechado | #0F172A |
| Fundo claro | Branco | #FFFFFF |
| Texto no escuro | Slate Claro | #F8FAFC |
| "Serv" no claro | Cinza Neutro | #64748B |
| "Serv" no escuro | Cinza Claro | #94A3B8 (mais legível que #64748B sobre o fundo escuro) |

Cores de destaque por nicho (svg/nichos e png/app/nichos): barbearia #F59E0B, beleza #EC4899, pet #06B6D4, saúde #0284C7, fitness #84CC16.

Fonte: Plus Jakarta Sans — "Sync" em ExtraBold (800), "Serv" em Medium (500). Nos SVG o texto já está em curvas.

## Onde usar
**WhatsApp:** png/whatsapp/perfil-640.png (foto de perfil; o símbolo já cabe no recorte circular), status-1080x1920.png.
**App:** png/app/icon-1024.png (lojas e Expo: mobile/assets/icon.png), adaptive-icon-foreground-1024.png (fundo #0F172A no app.json), splash-icon-1024.png, play-store-512.png. icon-squircle-1024.png é só para apresentações (as lojas aplicam o arredondamento sozinhas). png/app/nichos/: ícones na cor de cada nicho.
**Site / landing page:** svg/horizontal (cabeçalho), favicon.ico + favicon.svg, apple-touch-icon-180.png, android-chrome-192/512.png, og-image-1200x630.png (prévia do link no WhatsApp e redes).
**Redes sociais:** png/social/ (post, post claro, story, capa).
**Impressão, Canva, Figma:** pasta svg/.

## Regras rápidas
- Fundo claro: versão azul e verde. Fundo escuro: versão em degradê com o nome em branco, ou azul e verde.
- Abaixo de 48 px, use só o símbolo; os favicons já usam a versão simplificada (traço mais grosso).
- Não distorça, não gire, não mude as cores fora da paleta e não aplique sombra.

```html
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon-180.png">
<meta property="og:image" content="https://SEU_DOMINIO/og-image-1200x630.png">
```
