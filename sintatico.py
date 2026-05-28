# -=-=-=-=-=-=-=-=-=-=-
#      Sintát-Ió
# -=-=-=-=-=-=-=-=-=-=-

import sys
from sly import Parser
from lexico import CoolLexer 

# pip install sly
# pyright: reportUndefinedVariable=false

class CoolParser(Parser):
    tokens = CoolLexer.tokens

    # -=-=- Tabela de Precedência -=-=-
    
    precedence = (
        ('right', 'IN'),
        ('right', 'ASSIGN'),
        ('left', 'NOT'),
        ('nonassoc', '<', '=', 'LE'),
        ('left', '+', '-'),
        ('left', '*', '/'),
        ('left', 'ISVOID'),
        ('left', '~'),
        ('left', '@'),
        ('left', '.')
    )

    # -=-=- Classes -=-=-
    
    @_('class_list')
    def program(self, p):
        return p.class_list

    @_('class_decl ";"')
    def class_list(self, p):
        return [p.class_decl]

    @_('class_list class_decl ";"')
    def class_list(self, p):
        return p.class_list + [p.class_decl]

    @_('CLASS TYPEID "{" feature_list "}"')
    def class_decl(self, p):
        return ('Classe', p.TYPEID, 'Object', p.feature_list)

    @_('CLASS TYPEID INHERITS TYPEID "{" feature_list "}"')
    def class_decl(self, p):
        return ('Classe', p.TYPEID0, p.TYPEID1, p.feature_list)


    # -=-=- Features -=-=-
    
    @_('')
    def feature_list(self, p):
        return []

    @_('feature_list feature ";"')
    def feature_list(self, p):
        return p.feature_list + [p.feature]

    @_('OBJECTID ":" TYPEID')
    def feature(self, p):
        return ('Atributo', p.OBJECTID, p.TYPEID, None)

    @_('OBJECTID ":" TYPEID ASSIGN expr')
    def feature(self, p):
        return ('Atributo', p.OBJECTID, p.TYPEID, p.expr)

    @_('OBJECTID "(" formal_list ")" ":" TYPEID "{" expr "}"')
    def feature(self, p):
        return ('Metodo', p.OBJECTID, p.formal_list, p.TYPEID, p.expr)

    @_('OBJECTID "(" ")" ":" TYPEID "{" expr "}"')
    def feature(self, p):
        return ('Metodo', p.OBJECTID, [], p.TYPEID, p.expr)


    # -=-=- Formals -=-=-
    
    @_('formal')
    def formal_list(self, p):
        return [p.formal]

    @_('formal_list "," formal')
    def formal_list(self, p):
        return p.formal_list + [p.formal]

    @_('OBJECTID ":" TYPEID')
    def formal(self, p):
        return ('Parametro', p.OBJECTID, p.TYPEID)


    # -=-=- Expressões -=-=-
    
    @_('OBJECTID ASSIGN expr')
    def expr(self, p): return ('Atribuicao', p.OBJECTID, p.expr)

    @_('expr "." OBJECTID "(" expr_list_comma ")"')
    def expr(self, p): return ('Chamada', p.expr, p.OBJECTID, p.expr_list_comma)

    @_('expr "." OBJECTID "(" ")"')
    def expr(self, p): return ('Chamada', p.expr, p.OBJECTID, [])

    @_('expr "@" TYPEID "." OBJECTID "(" expr_list_comma ")"')
    def expr(self, p): return ('ChamadaEstatica', p.expr, p.TYPEID, p.OBJECTID, p.expr_list_comma)

    @_('expr "@" TYPEID "." OBJECTID "(" ")"')
    def expr(self, p): return ('ChamadaEstatica', p.expr, p.TYPEID, p.OBJECTID, [])

    @_('OBJECTID "(" expr_list_comma ")"')
    def expr(self, p): return ('ChamadaSelf', p.OBJECTID, p.expr_list_comma)

    @_('OBJECTID "(" ")"')
    def expr(self, p): return ('ChamadaSelf', p.OBJECTID, [])

    @_('IF expr THEN expr ELSE expr FI')
    def expr(self, p): return ('If', p.expr0, p.expr1, p.expr2)

    @_('WHILE expr LOOP expr POOL')
    def expr(self, p): return ('While', p.expr0, p.expr1)

    @_('"{" expr_list_semi "}"')
    def expr(self, p): return ('Bloco', p.expr_list_semi)

    @_('LET let_list IN expr')
    def expr(self, p): return ('Let', p.let_list, p.expr)

    @_('CASE expr OF case_list ESAC')
    def expr(self, p): return ('Case', p.expr, p.case_list)

    @_('NEW TYPEID')
    def expr(self, p): return ('New', p.TYPEID)

    @_('ISVOID expr')
    def expr(self, p): return ('IsVoid', p.expr)

    @_('expr "+" expr')
    def expr(self, p): return ('Soma', p.expr0, p.expr1)

    @_('expr "-" expr')
    def expr(self, p): return ('Subtracao', p.expr0, p.expr1)

    @_('expr "*" expr')
    def expr(self, p): return ('Multiplicacao', p.expr0, p.expr1)

    @_('expr "/" expr')
    def expr(self, p): return ('Divisao', p.expr0, p.expr1)

    @_('"~" expr')
    def expr(self, p): return ('NaoMatematico', p.expr)

    @_('expr "<" expr')
    def expr(self, p): return ('MenorQue', p.expr0, p.expr1)

    @_('expr LE expr')
    def expr(self, p): return ('MenorIgual', p.expr0, p.expr1)

    @_('expr "=" expr')
    def expr(self, p): return ('Igual', p.expr0, p.expr1)

    @_('NOT expr')
    def expr(self, p): return ('NaoLogico', p.expr)

    @_('"(" expr ")"')
    def expr(self, p): return p.expr

    @_('OBJECTID')
    def expr(self, p): return ('Variavel', p.OBJECTID)

    @_('INT_CONST')
    def expr(self, p): return ('Inteiro', p.INT_CONST)

    @_('STR_CONST')
    def expr(self, p): return ('Texto', p.STR_CONST)

    @_('BOOL_CONST')
    def expr(self, p): return ('Booleano', p.BOOL_CONST)


    # -=-=- Listas -=-=-
    
    @_('expr')
    def expr_list_comma(self, p): return [p.expr]

    @_('expr_list_comma "," expr')
    def expr_list_comma(self, p): return p.expr_list_comma + [p.expr]

    @_('expr ";"')
    def expr_list_semi(self, p): return [p.expr]

    @_('expr_list_semi expr ";"')
    def expr_list_semi(self, p): return p.expr_list_semi + [p.expr]

    @_('OBJECTID ":" TYPEID')
    def let_binding(self, p): return ('LetBind', p.OBJECTID, p.TYPEID, None)

    @_('OBJECTID ":" TYPEID ASSIGN expr')
    def let_binding(self, p): return ('LetBind', p.OBJECTID, p.TYPEID, p.expr)

    @_('let_binding')
    def let_list(self, p): return [p.let_binding]

    @_('let_list "," let_binding')
    def let_list(self, p): return p.let_list + [p.let_binding]

    @_('OBJECTID ":" TYPEID DARROW expr ";"')
    def case_branch(self, p): return ('CaseBranch', p.OBJECTID, p.TYPEID, p.expr)

    @_('case_branch')
    def case_list(self, p): return [p.case_branch]

    @_('case_list case_branch')
    def case_list(self, p): return p.case_list + [p.case_branch]


    # -=-=- Erros -=-=-
    
    def error(self, p):
        if p:
            print(f"Erro Sintático. Estrutura inesperada '{p.value}' na linha {p.lineno}... o mundo é cheio de surpresas... vai dar tudo certo.", file=sys.stderr)
        else:
            print("Erro Sintático. O arquivo termina do nada... mas tá tudo bem, todos nos terminamos um dia.", file=sys.stderr)
