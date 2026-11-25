import React, { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Reveal } from './Reveal'

interface FaqItem {
  id: string
  pergunta: string
  resposta: string
}

const DUVIDAS: FaqItem[] = [
  {
    id: 'tipos-documentos',
    pergunta: 'Quais tipos de documento o EviDocs reconhece?',
    resposta:
      'O sistema identifica 7 tipos trabalhistas: ASO, folha de pagamento, folha de ponto, holerite, recibo de férias, atestado médico e contrato de trabalho — mesmo quando chegam misturados em um único arquivo escaneado.',
  },
  {
    id: 'separar-pdfs',
    pergunta: 'Preciso separar os PDFs antes de enviar?',
    resposta:
      'Não. Você pode enviar o lote inteiro em um único PDF multipágina ou imagens. O EviDocs aplica OCR, identifica onde começa e termina cada documento, classifica por tipo e extrai campos como CNPJ, competência e matrícula.',
  },
  {
    id: 'ia-alucinacao',
    pergunta: 'A IA pode errar ou inventar uma divergência trabalhista?',
    resposta:
      'Na decisão, não. A IA apenas lê e extrai os dados do documento; os cálculos de jornada, as regras da CLT, Portaria 671 e EC 141 e a nota de 0 a 100 são executados em código determinístico. Todo apontamento mostra o artigo da lei e a página original ao lado, e casos de baixa confiança vão para a fila de revisão humana.',
  },
  {
    id: 'convencoes-ec141',
    pergunta: 'Como funcionam convenções coletivas e mudanças na lei (EC 141)?',
    resposta:
      'Cada contrato pode ter seu próprio perfil de jornada configurado conforme a convenção coletiva aplicável. Além disso, o calendário da EC 141 já está implementado na linha do tempo: 42 h semanais a partir de 16/12/2026 e 40 h a partir de 16/12/2027.',
  },
  {
    id: 'dados-pessoais',
    pergunta: 'Como os dados pessoais dos funcionários são tratados?',
    resposta:
      'Antes de enviar texto para os modelos de IA, o sistema aplica uma camada de anonimização determinística que mascara CPF, RG, PIS, data de nascimento e nomes, preservando apenas o necessário para a auditoria, como o CNPJ da terceirizada e as marcações de ponto.',
  },
  {
    id: 'piloto-cobranca',
    pergunta: 'Como funciona para testar em um piloto e qual é o modelo de cobrança?',
    resposta:
      'Os resultados publicados no site foram medidos em lotes simulados inéditos, e o próximo passo é validar com um lote real de cliente. A cobrança é por documento processado — com custo de IA abaixo de US$ 0,01 por documento comum, o valor no piloto é definido pelo volume e pelo tempo de análise economizado.',
  },
]

export const FaqSection: React.FC = () => {
  const [abertoId, setAbertoId] = useState<string | null>(DUVIDAS[0].id)

  const alternar = (id: string) => {
    setAbertoId((atual) => (atual === id ? null : id))
  }

  return (
    <div className="space-y-12">
      <Reveal className="max-w-3xl space-y-3">
        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#7e22ce] dark:text-[#f38df9]">
          Dúvidas frequentes
        </div>
        <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight text-[#2d0a33] dark:text-white">
          Perguntas comuns antes de rodar um piloto.
        </h2>
      </Reveal>

      <div className="space-y-3.5">
        {DUVIDAS.map((item, idx) => {
          const aberto = abertoId === item.id
          const painelId = `faq-painel-${item.id}`
          const botaoId = `faq-botao-${item.id}`

          return (
            <Reveal key={item.id} delayMs={idx * 55}>
              <div
                className={`rounded-2xl border transition-all duration-300 ${
                  aberto
                    ? 'border-[#bd79ff]/70 bg-white dark:bg-[#21122b] shadow-lg shadow-[#9333ea]/10'
                    : 'border-[#ece8ef] dark:border-[#281933] bg-white/85 dark:bg-[#190f1f]/85 hover:border-[#bd79ff]/50'
                }`}
              >
                <h3>
                  <button
                    id={botaoId}
                    type="button"
                    aria-expanded={aberto}
                    aria-controls={painelId}
                    onClick={() => alternar(item.id)}
                    className="w-full px-6 py-5 text-left flex items-center justify-between gap-4 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#bd79ff] rounded-2xl"
                  >
                    <span className="flex items-baseline gap-3.5">
                      <span
                        className={`text-xs font-mono font-bold shrink-0 ${
                          aberto
                            ? 'text-[#7e22ce] dark:text-[#5ddfff]'
                            : 'text-[#a394b0] dark:text-[#5c4b69]'
                        }`}
                      >
                        0{idx + 1}
                      </span>
                      <span className="text-base sm:text-lg font-bold text-[#2d0a33] dark:text-white leading-snug">
                        {item.pergunta}
                      </span>
                    </span>

                    <span
                      className={`p-1.5 rounded-lg shrink-0 transition-all duration-300 ${
                        aberto
                          ? 'bg-[#f4e8f7] dark:bg-[#311840] text-[#7e22ce] dark:text-[#f38df9] rotate-180'
                          : 'text-[#7a6d85] dark:text-[#9c8ea6]'
                      }`}
                    >
                      <ChevronDown className="w-4 h-4" />
                    </span>
                  </button>
                </h3>

                <div
                  id={painelId}
                  role="region"
                  aria-labelledby={botaoId}
                  className={`grid transition-[grid-template-rows,opacity] duration-300 ease-out ${
                    aberto ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
                  }`}
                >
                  <div className="overflow-hidden">
                    <p className="px-6 pb-6 pl-[3.25rem] text-sm sm:text-base text-[#5b4d66] dark:text-[#c7b9d2] leading-relaxed">
                      {item.resposta}
                    </p>
                  </div>
                </div>
              </div>
            </Reveal>
          )
        })}
      </div>
    </div>
  )
}
