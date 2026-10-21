/* SyncServ - landing page. JavaScript puro, sem dependências. */

// ---------------------------------------------------------------- configure aqui
// Número que recebe os pedidos de teste: só dígitos, com DDI e DDD (ex.: "5531999998888")
const WHATSAPP_NUMBER = "[NUMERO]";
// Número do robô de demonstração (instância do bot). Vazio = o botão "Falar com o robô de verdade" não aparece.
const DEMO_NUMBER = "";
// Preços exibidos nos planos (texto livre, ex.: "R$ 79")
const PRICES = { individual: "[PREÇO INDIVIDUAL]", equipe: "[PREÇO EQUIPE]" };

// ---------------------------------------------------------------- nichos
// accent: cor do nicho (preenchimentos); accentText: a mesma cor legível como texto sobre fundo escuro
const NICHES = {
  barbershop: {
    label: "Barbearia", business: "Sua Barbearia", welcome: "à Sua Barbearia", place: "na barbearia",
    symbol: "barbearia", accent: "#F59E0B", accentText: "#F59E0B",
    customer: "cliente", pro: "barbeiro", pros: "Nossos barbeiros", name: "Carlos",
    services: [["Corte", 30, 40], ["Barba", 30, 30], ["Corte + Barba", 60, 65]],
    team: ["João", "Pedro"], product: ["Pomada modeladora", 35],
    agenda: [["09:00", "Rafael Souza", "Corte", "in"], ["10:00", "Lucas Lima", "Corte + Barba", "paid"],
      ["11:30", "Bruno Alves", "Barba", "pend"], ["14:00", "Diego Rocha", "Corte", "pkg"]],
  },
  beauty: {
    label: "Salão de beleza", business: "Seu Salão", welcome: "ao Seu Salão", place: "no salão",
    symbol: "beleza", accent: "#EC4899", accentText: "#F472B6",
    customer: "cliente", pro: "profissional", pros: "Nossas profissionais", name: "Mariana",
    services: [["Escova", 45, 60], ["Corte feminino", 60, 90], ["Manicure e pedicure", 60, 55], ["Design de sobrancelha", 30, 40]],
    team: ["Ana Paula", "Carla", "Juliana"], product: ["Máscara de hidratação", 48],
    agenda: [["09:00", "Beatriz Gomes", "Escova", "in"], ["10:00", "Camila Rocha", "Corte feminino", "paid"],
      ["13:30", "Larissa Dias", "Manicure e pedicure", "pend"], ["15:00", "Renata Lopes", "Design de sobrancelha", "pkg"]],
  },
  petshop: {
    label: "Pet shop", business: "Seu Pet Shop", welcome: "ao Seu Pet Shop", place: "no pet shop",
    symbol: "pet", accent: "#06B6D4", accentText: "#22D3EE",
    customer: "tutor", pro: "profissional", pros: "Nossa equipe", name: "Fernanda",
    services: [["Banho porte pequeno", 60, 50], ["Banho e tosa", 90, 85], ["Tosa higiênica", 45, 40], ["Consulta veterinária", 30, 150]],
    team: ["Marcos", "Dra. Paula"], product: ["Shampoo neutro", 32],
    agenda: [["08:30", "Thor (Fernanda)", "Banho e tosa", "in"], ["10:00", "Mel (Patrícia)", "Banho porte pequeno", "paid"],
      ["11:00", "Bob (André)", "Consulta veterinária", "pend"], ["14:00", "Luna (Carlos)", "Tosa higiênica", "pkg"]],
  },
  clinic: {
    label: "Clínica", business: "Sua Clínica", welcome: "à Sua Clínica", place: "na clínica",
    symbol: "saude", accent: "#0284C7", accentText: "#38BDF8",
    customer: "paciente", pro: "profissional", pros: "Nossos profissionais", name: "Helena",
    services: [["Consulta clínica geral", 30, 200], ["Retorno", 20, 80], ["Fisioterapia", 50, 120], ["Nutrição", 45, 180]],
    team: ["Dr. Ricardo", "Dra. Fernanda"], product: ["Faixa elástica", 40],
    agenda: [["08:00", "Paulo Mendes", "Consulta clínica geral", "in"], ["09:00", "Sabrina Nunes", "Fisioterapia", "pkg"],
      ["10:30", "José Freitas", "Retorno", "pend"], ["14:00", "Vanessa Lima", "Nutrição", "paid"]],
  },
  fitness: {
    label: "Estúdio fitness", business: "Seu Estúdio", welcome: "ao Seu Estúdio", place: "no estúdio",
    symbol: "fitness", accent: "#84CC16", accentText: "#A3E635",
    customer: "aluno", pro: "professor", pros: "Nossos professores", name: "Gabriel",
    services: [["Aula de pilates", 50, 70], ["Treino funcional", 50, 60], ["Personal training", 60, 120], ["Avaliação física", 40, 90]],
    team: ["Bruno", "Camila"], product: ["Garrafa de água", 25],
    agenda: [["06:00", "Igor Santos", "Treino funcional", "in"], ["07:00", "Júlia Alves", "Aula de pilates", "pkg"],
      ["08:00", "Rafael Costa", "Personal training", "pend"], ["18:00", "Natália Reis", "Aula de pilates", "paid"]],
  },
};

let current = "barbershop";
const N = () => NICHES[current];
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const money = (v) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------------------------------------------------------------- WhatsApp
function waLink(number, text) {
  return `https://wa.me/${number}?text=${encodeURIComponent(text)}`;
}
function ctaText(kind, plan) {
  if (kind === "contact") return "Olá! Tenho uma dúvida sobre o SyncServ.";
  return `Olá! Quero testar o SyncServ grátis por 7 dias. Meu negócio é: ${N().label}`
    + (plan ? ` (plano ${plan})` : "");
}
function updateCtas() {
  $$(".js-cta").forEach((a) => {
    a.href = waLink(WHATSAPP_NUMBER, ctaText(a.dataset.msg, a.dataset.plan));
    a.target = "_blank";
    a.rel = "noopener";
  });
  const real = $(".js-demo-real");
  if (real && DEMO_NUMBER) {
    real.href = waLink(DEMO_NUMBER, "oi");
    real.target = "_blank";
    real.rel = "noopener";
    real.hidden = false;
  }
}

// ---------------------------------------------------------------- texto com *negrito* (sem innerHTML)
function rich(el, text) {
  text.split(/(\*[^*\n]+\*)/).forEach((part) => {
    if (/^\*[^*]+\*$/.test(part)) {
      const b = document.createElement("b");
      b.textContent = part.slice(1, -1);
      el.appendChild(b);
    } else if (part) {
      el.appendChild(document.createTextNode(part));
    }
  });
  return el;
}
function bubble(text, who) {
  const d = document.createElement("div");
  d.className = `msg msg--${who}`;
  return rich(d, text);
}

// ---------------------------------------------------------------- datas da conversa
const WEEK = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
function nextDays() {
  const out = [];
  const d = new Date();
  for (let i = 0; out.length < 3 && i < 10; i++) {
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate() + i);
    if (x.getDay() === 0) continue;
    const base = `${WEEK[x.getDay()]} ${String(x.getDate()).padStart(2, "0")}/${String(x.getMonth() + 1).padStart(2, "0")}`;
    out.push(i === 0 ? `Hoje (${base})` : i === 1 ? `Amanhã (${base})` : base.charAt(0).toUpperCase() + base.slice(1));
  }
  return out;
}

// ---------------------------------------------------------------- mockups do hero
function renderMocks() {
  const n = N();
  const [svc, min, price] = n.services[0];
  const day = nextDays()[1];
  const chat = $(".js-mock-chat");
  chat.replaceChildren(
    bubble("Oi, quero agendar", "out"),
    bubble(`Olá, ${n.name}! Boas-vindas ${n.welcome}\n\n*1* - Agendar horário\n*2* - Meus agendamentos\n*3* - Serviços e preços`, "in"),
    bubble("1", "out"),
    bubble(`Qual serviço você quer?\n\n*1* - ${svc} (${min} min) - ${money(price)}`, "in"),
    bubble("1", "out"),
    bubble(`*Agendado!*\n\n*${svc}* com ${n.team[0]}\n${day} às 10:00\n${money(price)}\n\nTe mando um lembrete antes do horário.`, "in"),
  );
  const app = $(".js-mock-app");
  const total = n.agenda.reduce((t, a) => t + (n.services.find((s) => s[0] === a[2]) || [0, 0, 0])[2], 0);
  const stats = document.createElement("div");
  stats.className = "m-stats";
  const whole = total.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
  [["Hoje", String(n.agenda.length)], ["Previsto", whole]].forEach(([l, v]) => {
    const s = document.createElement("div");
    s.className = "m-stat";
    s.append(Object.assign(document.createElement("span"), { textContent: l }),
      Object.assign(document.createElement("b"), { textContent: v }));
    stats.appendChild(s);
  });
  const title = Object.assign(document.createElement("div"), { className: "m-title", textContent: "Agenda de hoje" });
  app.replaceChildren(stats, title, ...n.agenda.map((a) => apptRow(a)));
  renderComanda();
  renderWeb();
}

// Selos com os mesmos nomes do app
const TAGS = { in: "Chegou", paid: "Sinal pago", pend: "Aguardando sinal", pkg: "Pacote", sync: "A confirmar" };
const el = (tag, className, textContent) => Object.assign(document.createElement(tag), { className, textContent });

function apptRow([time, who, what, tag], short = false) {
  const row = el("div", "m-appt");
  const info = el("div", "");
  info.append(el("b", "", who), el("span", "", what));
  if (tag && !short) info.appendChild(el("small", `m-tag m-tag--${tag}`, TAGS[tag]));
  row.append(el("time", "", time), info);
  return row;
}

// Comanda no celular (sem internet): serviço do agendamento, produto, desconto, gorjeta e pagamento dividido
function renderComanda() {
  const n = N();
  const [, who, what] = n.agenda[1];
  const service = n.services.find((s) => s[0] === what) || n.services[0];
  const [product, pPrice] = n.product;
  const discount = 5;
  const tip = 10;
  const total = service[2] + pPrice - discount + tip;
  const pix = Math.round(total / 2);
  const line = (title, sub, value, opts = {}) => {
    const row = el("div", `m-line${opts.minus ? " m-line--minus" : ""}`);
    const info = el("div", "");
    info.append(el("b", "", title), el("span", "", sub));
    if (opts.tag) info.appendChild(el("small", `m-tag m-tag--${opts.tag}`, TAGS[opts.tag]));
    row.append(info, el("strong", "", (opts.minus ? "− " : "") + money(value)));
    return row;
  };
  const sum = el("div", "m-sum");
  [["Total", money(total)], ["Pix", money(pix)], ["Dinheiro", money(total - pix)], ["Falta", money(0)]].forEach(([l, v]) => {
    const d = el("div", "");
    d.append(el("span", "", l), el("span", "", v));
    sum.appendChild(d);
  });
  $$(".js-comanda-who").forEach((x) => { x.textContent = who; });
  $(".js-mock-comanda").replaceChildren(
    line(service[0], `${n.team[0]} · ${service[1]} min`, service[2]),
    line(product, "Produto · 1 un.", pPrice, { tag: "sync" }),
    line("Desconto", "na conta", discount, { minus: true }),
    line("Gorjeta", `para ${n.team[0]}`, tip),
    sum,
    el("div", "m-btn", "Fechar comanda"),
  );
}

// Versão web: agenda de cada profissional lado a lado
function renderWeb() {
  const n = N();
  const cols = n.team.map((pro, i) => {
    const col = el("div", "w-col");
    col.appendChild(el("b", "", pro));
    n.agenda.filter((_, j) => j % n.team.length === i).forEach((a) => col.appendChild(apptRow(a)));
    return col;
  });
  $(".js-mock-web").replaceChildren(...cols);
}

// ---------------------------------------------------------------- simulador do robô
const sim = { log: null, options: null, status: null, token: 0, state: {} };

// Rola a conversa até o fim no próximo quadro (evita forçar o layout logo depois de inserir)
function scrollLog() {
  requestAnimationFrame(() => { sim.log.scrollTop = sim.log.scrollHeight; });
}
function say(text, who) {
  sim.log.appendChild(bubble(text, who));
  scrollLog();
}
function note(text) {
  sim.log.appendChild(Object.assign(document.createElement("p"), { className: "sim__note", textContent: text }));
  scrollLog();
}
// Resposta do robô com "digitando..." e um pequeno atraso. token: descarta respostas de uma conversa reiniciada.
function bot(texts, options) {
  const token = sim.token;
  const list = Array.isArray(texts) ? texts : [texts];
  sim.options.replaceChildren();
  let chain = Promise.resolve();
  list.forEach((text) => {
    chain = chain.then(() => new Promise((resolve) => {
      if (token !== sim.token) return;
      sim.status.textContent = "digitando...";
      const typing = document.createElement("div");
      typing.className = "msg msg--in";
      typing.setAttribute("aria-label", "digitando");
      typing.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
      sim.log.appendChild(typing);
      scrollLog();
      const wait = reduced ? 150 : Math.min(1400, 550 + text.length * 6);
      setTimeout(() => {
        typing.remove();
        if (token !== sim.token) return;
        sim.status.textContent = "online";
        say(text, "in");
        resolve();
      }, wait);
    }));
  });
  chain.then(() => { if (token === sim.token) setOptions(options || []); });
}
function setOptions(options) {
  sim.options.replaceChildren(...options.map((o) => {
    if (o.cta) {
      const a = document.createElement("a");
      a.className = "btn btn--cta js-cta";
      a.dataset.msg = "trial";
      a.textContent = o.label;
      return a;
    }
    const b = document.createElement("button");
    b.type = "button";
    b.className = "opt";
    b.textContent = o.label;
    b.addEventListener("click", () => {
      $$(".opt", sim.options).forEach((x) => { x.disabled = true; });
      say(o.reply || o.label, "out");
      o.go();
    });
    return b;
  }));
  updateCtas();
}

function summary() {
  const s = sim.state;
  return `*${s.service[0]}* com ${s.pro}\n${s.day} às ${s.time}\n${money(s.service[2])}`;
}
const flow = {
  menu() {
    const n = N();
    bot(`Olá, ${n.name}! Boas-vindas ${n.welcome}\n\n*1* - Agendar horário\n*2* - Meus agendamentos\n*3* - Serviços e preços\n`
      + `*4* - ${n.pros}\n*5* - Horário de funcionamento e endereço\n*6* - Pagar agendamento via Pix\n*7* - Falar com a gente\n\n`
      + "Responda com o número da opção.", [
      { label: "1 - Agendar horário", reply: "1", go: flow.service },
      { label: "3 - Serviços e preços", reply: "3", go: flow.prices },
    ]);
  },
  prices() {
    const lines = N().services.map(([s, m, p]) => `${s} (${m} min) - ${money(p)}`).join("\n");
    bot(`*Serviços e preços*\n\n${lines}`, [{ label: "1 - Agendar horário", reply: "1", go: flow.service }]);
  },
  service() {
    const svcs = N().services;
    bot("Qual serviço você quer?\n\n" + svcs.map(([s, m, p], i) => `*${i + 1}* - ${s} (${m} min) - ${money(p)}`).join("\n"),
      svcs.map((svc, i) => ({ label: `${i + 1} - ${svc[0]}`, reply: String(i + 1), go: () => { sim.state.service = svc; flow.pro(); } })));
  },
  pro() {
    const n = N();
    const opts = n.team.map((p, i) => ({ label: `${i + 1} - ${p}`, reply: String(i + 1), go: () => { sim.state.pro = p; flow.day(); } }));
    opts.push({ label: `${n.team.length + 1} - Tanto faz`, reply: String(n.team.length + 1), go: () => { sim.state.pro = n.team[0]; flow.day(); } });
    bot(`Com qual ${n.pro}?\n\n` + n.team.map((p, i) => `*${i + 1}* - ${p}`).join("\n")
      + `\n*${n.team.length + 1}* - Tanto faz (primeiro disponível)`, opts);
  },
  day() {
    const days = nextDays();
    bot("Para qual dia?\n\n" + days.map((d, i) => `*${i + 1}* - ${d}`).join("\n"),
      days.map((d, i) => ({ label: `${i + 1} - ${d}`, reply: String(i + 1), go: () => { sim.state.day = d; flow.time(); } })));
  },
  time() {
    const times = ["09:00", "10:30", "14:00", "16:30"];
    bot(`Horários livres em *${sim.state.day}*:\n\n*1* - 09:00    *2* - 10:30\n*3* - 14:00    *4* - 16:30\n\nResponda com o número do horário.`,
      times.map((t, i) => ({ label: `${i + 1} - ${t}`, reply: String(i + 1), go: () => { sim.state.time = t; flow.confirm(); } })));
  },
  confirm() {
    bot(`Confirma o agendamento?\n\n${summary()}\n\n*1* - Confirmar\n*2* - Escolher outro horário\n*3* - Desistir`, [
      { label: "1 - Confirmar", reply: "1", go: flow.booked },
      { label: "2 - Outro horário", reply: "2", go: flow.time },
      { label: "3 - Desistir", reply: "3", go: () => bot("Tudo bem, não agendei nada. Quando quiser é só chamar!", [{ label: "Recomeçar", go: restart }]) },
    ]);
  },
  booked() {
    bot(`*Agendado!*\n\n${summary()}\n\nQuer adiantar o pagamento?\n\n*1* - Pagar agora via Pix\n*2* - Pagar ${N().place}`, [
      { label: "1 - Pagar agora via Pix", reply: "1", go: flow.pix },
      { label: `2 - Pagar ${N().place}`, reply: "2", go: () => bot(`Combinado, pagamento ${N().place}. Te mando um lembrete antes do horário!`, [
        { label: "Ver o lembrete", go: flow.reminder },
      ]) },
    ]);
  },
  pix() {
    const n = N();
    bot([`*Pagamento via Pix*\n\n${summary()}\n\nValor: *${money(sim.state.service[2])}*\nRecebedor: ${n.business}\n\n`
      + "Copie o código da próxima mensagem e cole no app do seu banco em *Pix > Copia e cola*.\n"
      + "Depois de pagar, responda *paguei* (pode mandar o comprovante).",
    "00020126580014BR.GOV.BCB.PIX0136exemplo-de-chave-pix520400005303986540540.005802BR5913SUA EMPRESA6009SAO PAULO62070503***6304ABCD"], [
      { label: "paguei", go: flow.paid },
    ]);
  },
  paid() {
    const n = N();
    const token = sim.token;
    bot("Obrigado! Avisei a equipe. Assim que confirmarem o recebimento, te mando a confirmação.", []);
    setTimeout(() => {
      if (token !== sim.token) return; // a conversa foi reiniciada
      note(`${n.business} confere o extrato e confirma o Pix no app com um toque`);
      bot(`Recebemos o seu Pix de ${money(sim.state.service[2])}! Seu horário de ${sim.state.day} às ${sim.state.time} está pago. Até lá!`,
        [{ label: "Ver o lembrete", go: flow.reminder }]);
    }, reduced ? 200 : 1900);
  },
  reminder() {
    note("Antes do horário, o robô manda o lembrete");
    bot(`*Lembrete*, ${N().name}!\n\n${summary()}\n\n*1* - Confirmo presença\n*2* - Preciso cancelar`, [
      { label: "1 - Confirmo presença", reply: "1", go: () => bot("Presença confirmada! Até já.", flow.endOptions()) },
      { label: "2 - Preciso cancelar", reply: "2", go: () => bot(
        "Seu horário foi cancelado e ficou livre para outra pessoa. Para marcar outro, mande *menu*.", flow.endOptions()) },
    ]);
  },
  endOptions() {
    return [{ cta: true, label: "Quero isso na minha empresa" }, { label: "Recomeçar", go: restart }];
  },
};

function restart() {
  sim.token += 1;
  sim.state = {};
  sim.log.replaceChildren();
  sim.options.replaceChildren();
  sim.status.textContent = "online";
  setOptions([{ label: "Oi", go: flow.menu }]);
  note("Toque em uma resposta para conversar com o robô");
}

// ---------------------------------------------------------------- troca de nicho
function setNiche(key) {
  if (!NICHES[key]) return;
  current = key;
  const n = N();
  const root = document.documentElement;
  root.style.setProperty("--accent", n.accent);
  root.style.setProperty("--accent-text", n.accentText);
  $$(".niche").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.niche === key)));
  $$(".js-niche-symbol").forEach((img) => { img.src = `assets/nichos/${n.symbol}.svg`; });
  $$(".js-business").forEach((el) => { el.textContent = n.business; });
  $$(".js-customer").forEach((el) => { el.textContent = n.customer; });
  $$(".js-pro").forEach((el) => { el.textContent = n.pro; });
  renderMocks();
  restart();
  updateCtas();
}

// ---------------------------------------------------------------- calculadora
function calc() {
  const v = (id) => Number($(`#${id}`).value);
  const appts = v("c-appts");
  const price = v("c-price");
  const days = v("c-days");
  const loss = v("c-loss");
  $("#o-appts").textContent = appts;
  $("#o-price").textContent = money(price).replace(",00", "");
  $("#o-days").textContent = days;
  $("#o-loss").textContent = `${loss}%`;
  const total = (appts * price * days * loss) / 100;
  $("#calc-total").textContent = total.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

// ---------------------------------------------------------------- início
document.addEventListener("DOMContentLoaded", () => {
  // Menu do celular
  const btn = $(".menu-btn");
  const nav = $("#menu");
  const toggle = (open) => {
    nav.classList.toggle("is-open", open);
    btn.setAttribute("aria-expanded", String(open));
    btn.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
  };
  btn.addEventListener("click", () => toggle(btn.getAttribute("aria-expanded") !== "true"));
  $$("a", nav).forEach((a) => a.addEventListener("click", () => toggle(false)));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") toggle(false); });

  // Preços
  $$("[data-price]").forEach((el) => { el.textContent = PRICES[el.dataset.price] || el.textContent; });

  // Simulador
  sim.log = $(".js-sim-log");
  sim.options = $(".js-sim-options");
  sim.status = $(".js-sim-status");
  $(".js-sim-reset").addEventListener("click", restart);

  // Nichos
  $$(".niche").forEach((b) => b.addEventListener("click", () => setNiche(b.dataset.niche)));
  setNiche("barbershop");

  // Calculadora (botões − e + ao lado do valor, que é difícil de acertar no dedo pelo controle deslizante)
  $$(".calc__form input").forEach((i) => i.addEventListener("input", calc));
  $$(".step").forEach((b) => b.addEventListener("click", () => {
    const input = $(`#${b.dataset.for}`);
    input.value = Math.min(Number(input.max), Math.max(Number(input.min), Number(input.value) + Number(b.dataset.step)));
    calc();
  }));
  calc();
});
