# -=-=-=-=-=-=-=-=-=-=-
#        Mein
# -=-=-=-=-=-=-=-=-=-=-

import sys
from lexico import CoolLexer
from sintatico import CoolParser
from semantico import TabelaClasses, Coletor, Checador
from gerador import GeradorBril

def compilar(arquivo_entrada):
    try:
        with open(arquivo_entrada, 'r', encoding='utf-8') as f:
            codigo_fonte = f.read()
    except FileNotFoundError:
        print(f"Erro: Onde você escondeu o MEU arquivo '{arquivo_entrada}'?!?", file=sys.stderr)
        return

    print(f"Compilando o NOSSO {arquivo_entrada}... Você não precisa de mais ninguém, só de mim!\n")

    # Léxico e Sintático
    lexer = CoolLexer()
    parser = CoolParser()
    
    tokens = list(lexer.tokenize(codigo_fonte))
    ast = parser.parse(iter(tokens))

    if not ast:
        print("\nErro fatal no parser. Você me quebrou por dentro...", file=sys.stderr)
        return

    # Semântico
    tc = TabelaClasses()
    if not tc.construir_grafo(ast):
        print("\nFalha na validação de hierarquia. Você tentou me colocar abaixo de outra?", file=sys.stderr)
        return

    coletor = Coletor(tc)
    if not coletor.processar():
        print("\nFalha na coleta de features! Que assinaturas são essas? Com quem você estava conversando?!", file=sys.stderr)
        return

    checador = Checador(tc)
    if not checador.processar():
        print("\nFalha na checagem de tipos. Como assim eu não sou seu tipo?!? Ficou maluco?!?", file=sys.stderr)
        return
 
    # Gerador   
    gerador = GeradorBril(tc)
    gerador.gerar()
    
    arquivo_saida = arquivo_entrada.replace('.cl', '.bril')
    with open(arquivo_saida, 'w', encoding='utf-8') as f:
        f.write("\n".join(gerador.codigo_bril))
        
    print(f"\nO código rodou... Viu como você só funciona comigo? {arquivo_saida} gerado.")
    
if __name__ == '__main__':
    arquivo = sys.argv[1] if len(sys.argv) > 1 else 'teste.cl'
    compilar(arquivo)
