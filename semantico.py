# -=-=-=-=-=-=-=-=-=-=-
#      Sem-Antics
# -=-=-=-=-=-=-=-=-=-=-

import sys

def erro(msg, prefixo="Semântico"):
    print(f"Erro {prefixo}: {msg}", file=sys.stderr)

class TabelaClasses:
    def __init__(self):
        self.erros = 0
        
        self.classes = {
            'Object': {'pai': None, 'herdavel': True, 'ast': None},
            'IO':     {'pai': 'Object', 'herdavel': True, 'ast': None},
            'Int':    {'pai': 'Object', 'herdavel': False, 'ast': None},
            'String': {'pai': 'Object', 'herdavel': False, 'ast': None},
            'Bool':   {'pai': 'Object', 'herdavel': False, 'ast': None}
        }

    def _erro(self, msg):
        erro(msg)
        self.erros += 1

    def construir_grafo(self, ast):
        if not ast: return False

        # Registragem de Classes
        for no in ast:
            if no[0] == 'Classe':
                _, nome, heranca, features = no
                
                if nome in self.classes:
                    self._erro(f"Erro Semântico: Classe '{nome}' já definida.")
                    continue
                
                if nome == 'SELF_TYPE':
                    self._erro("Erro Semântico: 'SELF_TYPE' como nome de classe.")
                    continue

                self.classes[nome] = {'pai': heranca, 'herdavel': True, 'ast': features}

        self._validar_heranca()
        if self.erros > 0: return False
            
        self._checar_ciclos()
        
        if 'Main' not in self.classes:
            self._erro("Erro Semântico: Classe 'Main' não encontrada.")
            
        return self.erros == 0

    def _validar_heranca(self):
        for nome, info in self.classes.items():
            pai = info['pai']
            if not pai: continue
                
            if pai not in self.classes:
                self._erro(f"Erro Semântico: Classe '{nome}' herda de classe não definida '{pai}'.")
                info['pai'] = 'Object' # Fallback, herda de Object
            elif not self.classes[pai]['herdavel']:
                self._erro(f"Erro Semântico: Classe '{nome}' não pode herdar do built-in '{pai}'.")

    # Detecta loops de herança via Depth-First Search
    def _checar_ciclos(self):
        visitados, path = set(), set()

        def dfs(nome):
            if nome in path:
                self._erro(f"Herança cíclica detectada em '{nome}'.")
                return True
            if nome in visitados or not self.classes[nome]['pai']:
                return False

            path.add(nome)
            tem_ciclo = dfs(self.classes[nome]['pai'])
            path.remove(nome)
            visitados.add(nome)
            return tem_ciclo

        for c in self.classes:
            if c not in visitados: dfs(c)

class Coletor:
    def __init__(self, tabela_classes):
        self.tc = tabela_classes
        self.erros = 0

    def _erro(self, msg):
        erro(msg, "Passagem 3")
        self.erros += 1

    def processar(self):
        self._coletar('Object')
        return self.erros == 0

    def _coletar(self, classe_atual):
        info = self.tc.classes[classe_atual]
        info.setdefault('metodos', {})
        info.setdefault('atributos', {})

        # Herança de métodos e atributos
        pai = info['pai']
        if pai and pai in self.tc.classes:
            info_pai = self.tc.classes[pai]
            info['metodos'] = {n: sig.copy() for n, sig in info_pai.get('metodos', {}).items()}
            info['atributos'] = info_pai.get('atributos', {}).copy()

        self._injetar_builtins(classe_atual, info)

        # Processar features da AST local
        if info['ast']:
            for feature in info['ast']:
                if feature[0] == 'Atributo': self._validar_attr(classe_atual, feature)
                elif feature[0] == 'Metodo': self._validar_metodo(classe_atual, feature)

        # Descer na árvore
        for filho, f_info in self.tc.classes.items():
            if f_info['pai'] == classe_atual and filho != classe_atual:
                self._coletar(filho)

    def _injetar_builtins(self, nome, info):
        builtins = {
            'Object': {
                'abort': {'params': [], 'retorno': 'Object'},
                'type_name': {'params': [], 'retorno': 'String'},
                'copy': {'params': [], 'retorno': 'SELF_TYPE'}
            },
            'IO': {
                'out_string': {'params': ['String'], 'retorno': 'SELF_TYPE'},
                'out_int': {'params': ['Int'], 'retorno': 'SELF_TYPE'},
                'in_string': {'params': [], 'retorno': 'String'},
                'in_int': {'params': [], 'retorno': 'Int'}
            },
            'String': {
                'length': {'params': [], 'retorno': 'Int'},
                'concat': {'params': ['String'], 'retorno': 'String'},
                'substr': {'params': ['Int', 'Int'], 'retorno': 'String'}
            }
        }
        if nome in builtins:
            info['metodos'].update(builtins[nome])

    def _validar_attr(self, classe, no):
        _, nome, tipo, _ = no
        info = self.tc.classes[classe]

        if nome == 'self':
            return self._erro(f"Erro Semântico: [{classe}] 'self' não pode ser atributo.")

        if info['pai'] and nome in self.tc.classes[info['pai']].get('atributos', {}):
            return self._erro(f"Erro Semântico: [{classe}] Não é permitido sobrescrever o atributo herdado '{nome}'.")

        if nome in info.get('attrs_locais', {}):
            return self._erro(f"Erro Semântico: [{classe}] Atributo '{nome}' duplicado.")
        
        info.setdefault('attrs_locais', {})[nome] = tipo
        info['atributos'][nome] = tipo

    def _validar_metodo(self, classe, no):
        _, nome, params_ast, tipo_ret, _ = no
        info = self.tc.classes[classe]

        params = []
        vistos = set()
        for _, p_nome, p_tipo in params_ast:
            if p_nome == 'self':
                self._erro(f"Erro Semântico: [{classe}::{nome}] 'self' não pode ser parâmetro.")
            if p_nome in vistos:
                self._erro(f"Erro Semântico: [{classe}::{nome}] Parâmetro '{p_nome}' duplicado.")
            
            vistos.add(p_nome)
            params.append(p_tipo)

        assinatura = {'params': params, 'retorno': tipo_ret}

        # Checar validade de override
        if info['pai'] and nome in self.tc.classes[info['pai']].get('metodos', {}):
            pai_sig = self.tc.classes[info['pai']]['metodos'][nome]
            if pai_sig['params'] != assinatura['params'] or pai_sig['retorno'] != assinatura['retorno']:
                self._erro(f"Erro Semântico: [{classe}]: '{nome}' incompatível com o método pai.")

        info['metodos'][nome] = assinatura

# Simula escopo via uma lista de dicionarios, tipo pilha
class Escopo:
    def __init__(self):
        self.niveis = [{}]

    def push(self): self.niveis.append({})
    
    def pop(self):
        if len(self.niveis) > 1: self.niveis.pop()

    def add(self, nome, tipo):
        if nome in self.niveis[-1]: return False
        self.niveis[-1][nome] = tipo
        return True

    def get(self, nome):
        for n in reversed(self.niveis):
            if nome in n: return n[nome]
        return None


class Checador:
    def __init__(self, tabela_classes):
        self.tc = tabela_classes.classes
        self.escopo = Escopo()
        self.erros = 0
        self.classe_atual = None

    def _erro(self, msg):
        erro(msg, "Passagem 4")
        self.erros += 1

    def processar(self):
        for nome, info in self.tc.items():
            if not info.get('ast'): continue
            
            self.classe_atual = nome
            self.escopo.push()
            self.escopo.add('self', 'SELF_TYPE')
            
            for attr, tipo in info.get('atributos', {}).items():
                self.escopo.add(attr, tipo)

            for feature in info['ast']:
                self.visit(feature)
                
            self.escopo.pop()
            self.classe_atual = None

        return self.erros == 0

    def conforma(self, t1, t2):
        if t1 == t2 or t2 == 'Object': return True
        if t2 == 'SELF_TYPE': return False
        
        atual = self.classe_atual if t1 == 'SELF_TYPE' else t1
        while atual:
            if atual == t2: return True
            atual = self.tc.get(atual, {}).get('pai')
        return False

    def lub(self, t1, t2):
        if t1 == t2: return t1
        
        a = self.classe_atual if t1 == 'SELF_TYPE' else t1
        b = self.classe_atual if t2 == 'SELF_TYPE' else t2
        
        ancestrais = set()
        while a:
            ancestrais.add(a)
            a = self.tc.get(a, {}).get('pai')
            
        while b:
            if b in ancestrais: return b
            b = self.tc.get(b, {}).get('pai')
            
        return 'Object'

    def visit(self, no):
        if not isinstance(no, tuple):
            if isinstance(no, list):
                tipo = 'Object'
                for item in no: tipo = self.visit(item)
                return tipo
            return 'Object'

        # Dinamicamente chama visit_TipoDoNo ou cai no visit_Padrao
        metodo = getattr(self, f'visit_{no[0]}', self.visit_Padrao)
        return metodo(no)

    # --- Visitantes da AST ---

    def visit_Atributo(self, no):
        _, nome, t_decl, expr = no
        if expr:
            t_expr = self.visit(expr)
            if not self.conforma(t_expr, t_decl):
                self._erro(f"Erro Semântico: '{nome}': impossível atribuir '{t_expr}' a '{t_decl}'.")

    def visit_Metodo(self, no):
        _, nome, params, t_ret, expr = no
        self.escopo.push()
        
        for _, p_nome, p_tipo in params:
            self.escopo.add(p_nome, p_tipo)
            
        t_corpo = self.visit(expr)
        if not self.conforma(t_corpo, t_ret):
            self._erro(f"Erro Semântico: Metodo '{nome}': retorna '{t_corpo}', mas pede '{t_ret}'.")
            
        self.escopo.pop()

    def visit_Atribuicao(self, no):
        _, nome, expr = no
        t_var = self.escopo.get(nome)
        if not t_var:
            self._erro(f"Erro Semântico: Atribuição a variável não declarada: '{nome}'.")
            t_var = 'Object'
            
        t_expr = self.visit(expr)
        if not self.conforma(t_expr, t_var):
            self._erro(f"Erro Semântico: Não pode atribuir '{t_expr}' em '{nome}' ({t_var}).")
        return t_expr

    def _call(self, t_expr, nome_metodo, args, chamador_real):
        t_args = [self.visit(arg) for arg in args]
        classe_busca = self.classe_atual if chamador_real == 'SELF_TYPE' else chamador_real
        metodo = self.tc.get(classe_busca, {}).get('metodos', {}).get(nome_metodo)
        
        if not metodo:
            self._erro(f"Erro Semântico: Método '{nome_metodo}' inexistente em '{classe_busca}'.")
            return 'Object'
            
        params = metodo['params']
        if len(params) != len(t_args):
            self._erro(f"Erro Semântico: Chamada '{nome_metodo}': Esperava {len(params)}, recebeu {len(t_args)}.")
            return metodo['retorno']
            
        for i, (fornecido, esperado) in enumerate(zip(t_args, params)):
            if not self.conforma(fornecido, esperado):
                self._erro(f"Erro Semântico: Chamada '{nome_metodo}': Argumento {i+1} é '{fornecido}', esperava '{esperado}'.")
                
        return t_expr if metodo['retorno'] == 'SELF_TYPE' else metodo['retorno']

    def visit_Chamada(self, no):
        return self._call(self.visit(no[1]), no[2], no[3], self.visit(no[1]))

    def visit_ChamadaSelf(self, no):
        return self._call('SELF_TYPE', no[1], no[2], 'SELF_TYPE')

    def visit_ChamadaEstatica(self, no):
        _, expr, t_estatico, nome, args = no
        t_expr = self.visit(expr)
        if not self.conforma(t_expr, t_estatico):
            self._erro(f"Erro Semântico: Cast estático (@): '{t_expr}' não conforma com '{t_estatico}'.")
        return self._call(t_expr, nome, args, t_estatico)

    def visit_If(self, no):
        if self.visit(no[1]) != 'Bool': self._erro("Erro Semântico: Condição do IF deve ser Bool.")
        return self.lub(self.visit(no[2]), self.visit(no[3]))

    def visit_While(self, no):
        if self.visit(no[1]) != 'Bool': self._erro("Erro Semântico: Condição do WHILE deve ser Bool.")
        self.visit(no[2])
        return 'Object'

    def visit_Bloco(self, no):
        tipo = 'Object'
        for ex in no[1]: tipo = self.visit(ex)
        return tipo

    def visit_Let(self, no):
        _, binds, corpo = no
        escopos = 0
        
        for _, nome, t_decl, expr_init in binds:
            if expr_init:
                t_init = self.visit(expr_init)
                if not self.conforma(t_init, t_decl):
                    self._erro(f"Erro Semântico: Let: '{t_init}' não conforma com '{t_decl}' em '{nome}'.")
            self.escopo.push()
            self.escopo.add(nome, t_decl)
            escopos += 1
            
        t_corpo = self.visit(corpo)
        for _ in range(escopos): self.escopo.pop()
        return t_corpo

    def visit_Case(self, no):
        self.visit(no[1])
        t_branch, vistos = [], set()
        
        for _, nome, t_decl, expr in no[2]:
            if t_decl in vistos:
                self._erro(f"Erro Semântico: Case: Tipo '{t_decl}' duplicado nas ramificações.")
            vistos.add(t_decl)
            
            self.escopo.push()
            self.escopo.add(nome, t_decl)
            t_branch.append(self.visit(expr))
            self.escopo.pop()
            
        if not t_branch: return 'Object'
        
        res = t_branch[0]
        for t in t_branch[1:]: res = self.lub(res, t)
        return res

    def visit_New(self, no): return no[1]
    def visit_IsVoid(self, no): 
        self.visit(no[1])
        return 'Bool'

    def _op_aritmetica(self, no, op):
        t1, t2 = self.visit(no[1]), self.visit(no[2])
        if t1 != 'Int' or t2 != 'Int': self._erro(f"Erro Semântico: '{op}' exige Int (recebeu {t1}, {t2}).")
        return 'Int'

    def visit_Soma(self, no): return self._op_aritmetica(no, '+')
    def visit_Subtracao(self, no): return self._op_aritmetica(no, '-')
    def visit_Multiplicacao(self, no): return self._op_aritmetica(no, '*')
    def visit_Divisao(self, no): return self._op_aritmetica(no, '/')
    
    def visit_NaoMatematico(self, no):
        if self.visit(no[1]) != 'Int': self._erro("Erro Semântico: '~' exige Int.")
        return 'Int'

    def _op_cmp(self, no, op):
        t1, t2 = self.visit(no[1]), self.visit(no[2])
        if t1 != 'Int' or t2 != 'Int': self._erro(f"Erro Semântico: '{op}' exige Int.")
        return 'Bool'

    def visit_MenorQue(self, no): return self._op_cmp(no, '<')
    def visit_MenorIgual(self, no): return self._op_cmp(no, '<=')

    def visit_Igual(self, no):
        t1, t2 = self.visit(no[1]), self.visit(no[2])
        primitivos = {'Int', 'String', 'Bool'}
        if (t1 in primitivos or t2 in primitivos) and t1 != t2:
            self._erro(f"Erro Semântico: Não pode comparar primitivo '{t1}' com '{t2}'.")
        return 'Bool'

    def visit_NaoLogico(self, no):
        if self.visit(no[1]) != 'Bool': self._erro("Erro Semântico: 'not' exige Bool.")
        return 'Bool'

    def visit_Variavel(self, no):
        tipo = self.escopo.get(no[1])
        if not tipo:
            self._erro(f"Erro Semântico: Variavel '{no[1]}' não declarada.")
            return 'Object'
        return tipo

    def visit_Inteiro(self, no): return 'Int'
    def visit_Texto(self, no): return 'String'
    def visit_Booleano(self, no): return 'Bool'
    def visit_Padrao(self, no): return 'Object'
