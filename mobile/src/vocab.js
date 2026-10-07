// Termos de cada segmento. As telas usam v.pro, v.customer etc. no lugar de textos fixos.
// "Barbeiro(s)" só aparece no segmento barbershop.

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

const BASE = {
  barbershop: {
    business: 'barbearia', art: 'a',
    pro: 'barbeiro', pros: 'barbeiros', proHint: 'barbeiro',
    customer: 'cliente', customers: 'clientes',
    service: 'atendimento', services: 'atendimentos', serviceExample: 'Ex.: Corte degradê', fem: false,
  },
  beauty: {
    business: 'salão', art: 'o',
    pro: 'profissional', pros: 'profissionais', proHint: 'profissional',
    customer: 'cliente', customers: 'clientes',
    service: 'atendimento', services: 'atendimentos', serviceExample: 'Ex.: Escova progressiva', fem: false,
  },
  petshop: {
    business: 'pet shop', art: 'o',
    pro: 'tosador', pros: 'tosadores', proHint: 'tosador ou veterinário',
    customer: 'tutor', customers: 'tutores',
    service: 'atendimento', services: 'atendimentos', serviceExample: 'Ex.: Banho e tosa', fem: false,
  },
  clinic: {
    business: 'clínica', art: 'a',
    pro: 'profissional', pros: 'profissionais', proHint: 'profissional de saúde',
    customer: 'paciente', customers: 'pacientes',
    service: 'consulta', services: 'consultas', serviceExample: 'Ex.: Consulta de retorno', fem: true,
  },
  fitness: {
    business: 'estúdio', art: 'o',
    pro: 'professor', pros: 'professores', proHint: 'professor ou personal',
    customer: 'aluno', customers: 'alunos',
    service: 'aula', services: 'aulas', serviceExample: 'Ex.: Aula de pilates', fem: true,
  },
};

export function vocab(niche) {
  const b = BASE[niche] || BASE.barbershop;
  return {
    ...b,
    Business: cap(b.business),
    theBusiness: `${b.art} ${b.business}`, // "a barbearia", "o salão"
    Pro: cap(b.pro), Pros: cap(b.pros),
    Customer: cap(b.customer), Customers: cap(b.customers),
    Service: cap(b.service), Services: cap(b.services),
    // Concordância com o gênero do atendimento (consulta e aula são femininas)
    aService: `${b.fem ? 'uma' : 'um'} ${b.service}`, // "um atendimento", "uma consulta"
    noService: `${b.fem ? 'Nenhuma' : 'Nenhum'} ${b.service}`, // "Nenhum atendimento"
    allServices: `${b.fem ? 'Todas as' : 'Todos os'} ${b.services}`,
    done: b.fem ? 'concluída' : 'concluído', // "Consulta concluída"
    doneMany: b.fem ? 'concluídas' : 'concluídos',
    // "1 atendimento", "3 consultas"
    count: (n, one, many) => `${n} ${n === 1 ? one : many}`,
  };
}

// Vocabulário neutro (login, telas sem negócio carregado)
export const NEUTRAL = vocab('beauty');
