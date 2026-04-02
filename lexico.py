# -=-=-=-=-=-=-=-=-=-=-
#      Lexundere
# -=-=-=-=-=-=-=-=-=-=-

import sys
from sly import Lexer

# pip install sly
# pyright: reportUndefinedVariable=false

# -=-=- Lex -=-=-

class CoolLexer(Lexer):
    
    # -=-=- Tokens -=-=-
    
    tokens = {
        'CLASS', 'ELSE', 'FI', 'IF', 'IN', 'INHERITS', 'LET', 'LOOP', 'POOL', 'THEN', 'WHILE', 
        'CASE', 'ESAC', 'OF', 'DARROW', 'NEW', 'ISVOID', 'ASSIGN', 'NOT', 'LE',
        'STR_CONST', 'INT_CONST', 'BOOL_CONST', 'TYPEID', 'OBJECTID'
    }
    
    literals = { '+', '-', '*', '/', '~', '<', '=', '(', ')', '{', '}', '[', ']', '.', ',', ';', ':', '@' }
    
    DARROW = r'=>'
    ASSIGN = r'<-'
    LE     = r'<='

    ignore = ' \t\r\f\v'
    
    KEYWORDS = {
        'class': 'CLASS', 'else': 'ELSE', 'fi': 'FI', 'if': 'IF', 'in': 'IN',
        'inherits': 'INHERITS', 'let': 'LET', 'loop': 'LOOP', 'pool': 'POOL',
        'then': 'THEN', 'while': 'WHILE', 'case': 'CASE', 'esac': 'ESAC',
        'of': 'OF', 'new': 'NEW', 'isvoid': 'ISVOID', 'not': 'NOT'
    }

    # -=-=- Regras -=-=-
    
    # Contador de linhas
    @_(r'\n+')
    def ignore_newline(self, t):
        self.lineno += len(t.value)

    # Comentários de uma linha
    @_(r'--.*')
    def ignore_line_comment(self, t):
        pass

    # Booleanos
    @_(r'(t[rR][uU][eE])|(f[aA][lL][sS][eE])')
    def BOOL_CONST(self, t):
        t.value = True if t.value[0] == 't' else False
        return t
    
    # Identificador de tipo
    @_(r'[A-Z][a-zA-Z0-9_]*')
    def TYPEID(self, t):
        val_lower = t.value.lower()
        if val_lower in self.KEYWORDS:
            t.type = self.KEYWORDS[val_lower]
        return t

    # Identificador de objeto
    @_(r'[a-z][a-zA-Z0-9_]*')
    def OBJECTID(self, t):
        val_lower = t.value.lower()
        if val_lower in self.KEYWORDS:
            t.type = self.KEYWORDS[val_lower]
        return t
    
    # Inteiros
    @_(r'\d+')
    def INT_CONST(self, t):
        t.value = int(t.value)
        return t

    # Comentários de várias linhas
    @_(r'\(\*')
    def BLOCK_COMMENT(self, t):
        comment_depth = 1
        
        while comment_depth > 0 and self.index < len(self.text):
            if self.text.startswith('(*', self.index):
                # Pula o (*
                comment_depth += 1
                self.index += 2
            elif self.text.startswith('*)', self.index):
                # Pula o *)
                comment_depth -= 1
                self.index += 2
            else:
                # Avança um caractere normal
                if self.text[self.index] == '\n':
                    self.lineno += 1
                self.index += 1
        
        if comment_depth > 0:
            print(f"Erro léxico. Ignorante. Você não fechou um comentário na linha {self.lineno}", file=sys.stderr)

    # Strings
    @_(r'"')
    def STR_CONST(self, t):
        string_val = ""
        has_error = False

        while self.index < len(self.text):
            c = self.text[self.index]
            
            # Rejeita caracteres nulos
            if c == '\0':
                if not has_error:
                    print(f"Erro léxico seu jumento. A String possui um caractere nulo na linha {self.lineno}", file=sys.stderr)
                    has_error = True
                self.index += 1
                continue

            # Fim da String
            if c == '"':
                self.index += 1
                
                # Rejeita strings giganormes
                if len(string_val) >= 1024 and not has_error:
                    print(f"Erro léxico fião. Tá escrevendo a bíblia é? String muito longa na linha {self.lineno}", file=sys.stderr)
                    has_error = True

                if has_error:
                    return None
                
                t.value = string_val
                return t
            
            # Caracteres escapados
            elif c == '\\':
                self.index += 1
                if self.index < len(self.text):
                    nxt = self.text[self.index]
                    
                    # Rejeita caracteres nulos... novamente...
                    if nxt == '\0':
                        if not has_error:
                            print(f"Erro léxico seu jumento. A String possui um caractere nulo na linha {self.lineno}", file=sys.stderr)
                            has_error = True
                    elif nxt == 'n': string_val += '\n'
                    elif nxt == 't': string_val += '\t'
                    elif nxt == 'b': string_val += '\b'
                    elif nxt == 'f': string_val += '\f'
                    elif nxt == '\n': # Sim, aparentemente isso é válido. Realmente, é um COOL.
                        string_val += '\n'
                        self.lineno += 1
                    else: 
                        string_val += nxt
                    self.index += 1
            
            # Quebra de linha não escapada
            elif c == '\n':
                if not has_error:
                    print(f"Erro léxico. Esqueceu de escapar o \\n na linha {self.lineno} foi? Um completo animal.", file=sys.stderr)
                self.lineno += 1
                self.index += 1
                return None 
            
            # Texto da string usual 
            else:
                string_val += c
                self.index += 1
                
        # Fim do arquivo sem fechar a String
        if not has_error:
            print(f"Erro léxico meu patrão. Desmaiou no computador foi? Texto termina numa String aberta!", file=sys.stderr)
        return None

    # Caractere Ilegal
    def error(self, t):
        print(f"Erro léxico. Idiota. Tem um caractere ilegal '{t.value[0]}' na linha {self.lineno}", file=sys.stderr)
        self.index += 1


# -=-=- Execução -=-=-

if __name__ == '__main__':

    if len(sys.argv) > 1:
        arquivo_entrada = sys.argv[1]
    else:
        arquivo_entrada = 'teste.cl'

    try:
        with open(arquivo_entrada, 'r', encoding='utf-8') as f:
            codigo_fonte = f.read()
            
        lexer = CoolLexer()
        
        for tok in lexer.tokenize(codigo_fonte):
            print(f"Linha: {tok.lineno:02d} | Token: {tok.type:10} | Valor: {tok.value}")
            
    except FileNotFoundError:
        print(f"Erro. Arquivo '{arquivo_entrada}' não encontrado. Imbecil.")