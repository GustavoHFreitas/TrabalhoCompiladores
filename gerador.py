# -=-=-=-=-=-=-=-=-=-=-
#       Gerador
# -=-=-=-=-=-=-=-=-=-=-

import sys

# A classe GeradorBril é o "Back-end" (parte final) do nosso compilador.
# Ela recebe a Tabela de Classes e a Árvore Sintática Abstrata (AST) que foram
# validadas pelo analisador semântico e as traduz para instruções Bril.
# Bril (Big Red Intermediate Language) é uma linguagem intermediária muito simples,
# semelhante à linguagem de máquina (Assembly), que suporta apenas operações básicas,
# saltos (jumps) e tipos primitivos como inteiros e booleanos. Não possui objetos nativos.
class GeradorBril:
    def __init__(self, tabela_classes):
        # Armazena a tabela de classes preenchida nas fases anteriores.
        self.tc = tabela_classes.classes
        
        # Lista que armazenará todas as linhas de código Bril geradas.
        self.codigo_bril = []
        
        # Contadores para criar variáveis e rótulos (labels) com nomes únicos.
        # Em Bril, cada resultado intermediário precisa ser salvo em uma variável temporária.
        self.temp_var_count = 0
        self.label_count = 0
        
        # Rastreia qual classe está sendo compilada no momento.
        self.classe_atual = None
        
        # O "Environment" (Ambiente) mapeia os nomes das variáveis do Cool 
        # para os nomes temporários únicos que geramos no Bril.
        self.env = {}
        
        # Como o Bril não sabe o que é uma "Classe", nós atribuímos um número
        # de identificação (Class ID) único para cada classe. 
        # Isso será salvo na memória do objeto para sabermos seu tipo em tempo de execução.
        self.class_ids = {nome: i for i, nome in enumerate(self.tc.keys())}
        
        # Dicionário contendo as assinaturas dos métodos padrão (built-ins) do Cool.
        # Como o Cool espera que esses métodos existam, precisamos gerá-los manualmente em Bril.
        self.builtins = {
            'IO': [('out_string', ['x']), ('out_int', ['x']), ('in_string', []), ('in_int', [])],
            'Object': [('abort', []), ('type_name', []), ('copy', [])],
            'String': [('length', []), ('concat', ['s']), ('substr', ['i', 'l'])]
        }
        
        # Constrói o mapa de memória (onde cada atributo fica salvo no objeto).
        self._build_layouts()
        # Constrói a VTable (Tabela de Métodos Virtuais) para suportar herança.
        self._build_flat_vtable()

    # O Layout de Memória define como os atributos de uma classe são organizados fisicamente.
    # Quando alocamos um objeto no Bril, criamos um array de inteiros.
    # O índice 0 sempre guarda o Class ID. Os índices seguintes guardam os atributos.
    def _build_layouts(self):
        self.layouts = {} # Mapeia {NomeDaClasse: {NomeDoAtributo: PosicaoNaMemoria}}
        self.sizes = {}   # Mapeia {NomeDaClasse: TamanhoTotalNecessario}
        
        for cls in self.tc:
            # Reconstrói a árvore genealógica da classe (desde Object até a classe atual).
            hierarchy = []
            atual = cls
            while atual:
                hierarchy.insert(0, atual)
                atual = self.tc.get(atual, {}).get('pai')
            
            offset = 1 # O offset (deslocamento) começa em 1 porque o índice 0 é o Class ID.
            layout = {}
            
            # Percorre do pai mais distante até o filho atual para garantir que 
            # os atributos herdados fiquem nas mesmas posições de memória.
            for c in hierarchy:
                for a_name in self.tc.get(c, {}).get('atributos', {}):
                    if a_name not in layout:
                        layout[a_name] = offset
                        offset += 1 # Avança um espaço na memória para o próximo atributo.
            
            self.layouts[cls] = layout
            self.sizes[cls] = offset # O offset final é igual ao tamanho total do objeto.

    # A VTable (Virtual Method Table) "achata" a herança.
    # Se a classe Cachorro herda de Animal, a VTable de Cachorro copia
    # todos os métodos de Animal para dentro dela mesma, substituindo (overriding)
    # apenas os métodos que Cachorro reescreveu. Isso permite descobrir qual função chamar.
    def _build_flat_vtable(self):
        self.vtables = {cls: {} for cls in self.tc}
        for cls in self.tc:
            atual = cls
            hierarchy = []
            
            # Reconstrói a linhagem novamente.
            while atual:
                hierarchy.insert(0, atual)
                atual = self.tc.get(atual, {}).get('pai')
                
            for c in hierarchy:
                # Copia os métodos embutidos (built-ins) primeiro.
                if c in self.builtins:
                    for m_name, params in self.builtins[c]:
                        self.vtables[cls][m_name] = (c, params, None)
                
                # Depois copia os métodos definidos na árvore sintática (AST).
                # Se um filho definir um método com o mesmo nome, ele sobrescreve o do pai aqui.
                info = self.tc.get(c, {})
                if 'ast' in info and info['ast']:
                    for f in info['ast']:
                        if f[0] == 'Metodo':
                            m_name = f[1]
                            params = [p[1] for p in f[2]]
                            self.vtables[cls][m_name] = (c, params, f[4])

    # Método principal que orquestra a geração de todo o código Bril.
    def gerar(self):
        # 1. Gera a função responsável por alocar memória.
        self._gerar_allocator()
        
        # 2. Gera as funções padrões (IO, String, etc.).
        self._gerar_builtins_base()

        # 3. Gera todas as funções escritas pelo usuário no código Cool.
        for cls, methods in self.vtables.items():
            for m_name, (def_cls, params, ast_expr) in methods.items():
                # Só gera se a classe atual for a dona original da implementação
                # (evita gerar cópias duplicadas de métodos herdados que não mudaram).
                if def_cls == cls and ast_expr: 
                    self._gerar_metodo(cls, m_name, params, ast_expr)

        # 4. Gera as funções "roteadoras" (dispatchers) que resolvem polimorfismo.
        self._gerar_dispatchers()

        # 5. Gera o ponto de entrada (entry point) exigido pelo sistema operacional.
        self.emit("\n@main(input_arg: int) {")
        
        # Define o tamanho do nosso Heap (nossa memória global simulada).
        self.emit("  mem_sz: int = const 100000;")
        # A instrução 'alloc' do Bril pede uma quantidade de memória ao sistema.
        self.emit("  mem: ptr<int> = alloc mem_sz;")
        
        # O índice 0 da memória guarda o ponteiro para o próximo espaço livre.
        # Inicia em 2 porque os índices 0 e 1 são reservados para uso do sistema.
        self.emit("  two: int = const 2;")
        self.emit("  store mem two;")
        
        # O índice 1 da memória funciona como o nosso "Standard Input" (Teclado).
        # Salva o argumento passado na linha de comando lá para o in_int ler depois.
        self.emit("  one: int = const 1;")
        self.emit("  ptr_input: ptr<int> = ptradd mem one;")
        self.emit("  store ptr_input input_arg;")
        
        # Prepara a criação do objeto inicial da classe 'Main'.
        main_c_id = self.class_ids.get('Main', 0)
        main_sz = self.sizes.get('Main', 1)
        
        self.emit(f"  m_id: int = const {main_c_id};")
        self.emit(f"  m_sz: int = const {main_sz};")
        
        # Instancia o objeto Main chamando o nosso alocador de memória.
        self.emit("  main_obj: int = call @alloc_obj mem m_id m_sz;")
        
        # Inicia a execução do programa chamando o método main() do objeto instanciado.
        self.emit("  dummy_res: int = call @dispatch_main mem main_obj;")
        
        # Libera a memória de volta para o sistema operacional antes de fechar.
        self.emit("  free mem;")
        self.emit("}")

    # Função utilitária para adicionar uma linha de código à nossa lista final.
    def emit(self, instrucao):
        self.codigo_bril.append(instrucao)

    # Função utilitária que gera um nome único para uma nova variável temporária.
    def _new_temp(self):
        self.temp_var_count += 1
        return f"v_{self.temp_var_count}"

    # Função utilitária que gera um nome único para um novo bloco/rótulo de desvio.
    def _new_label(self, prefix="lbl"):
        self.label_count += 1
        return f"{prefix}_{self.label_count}"

    # Como armazenamos TUDO (inteiros, ponteiros, booleanos) como inteiros na memória,
    # precisamos de uma forma de converter um valor booleano nativo do Bril para um inteiro.
    # 0 = Falso, 1 = Verdadeiro. Usa saltos condicionais (br) para decidir qual valor salvar.
    def _bool_to_int(self, b_var):
        res = self._new_temp()
        lbl_t = self._new_label("bt_true")
        lbl_f = self._new_label("bt_false")
        lbl_e = self._new_label("bt_end")
        
        # Assume 0 (Falso) por padrão.
        self.emit(f"  {res}: int = const 0;")
        # Pula para o label True se b_var for verdadeiro, senão pula pro False.
        self.emit(f"  br {b_var} .{lbl_t} .{lbl_f};")
        
        self.emit(f".{lbl_t}:")
        self.emit(f"  {res}: int = const 1;") # Substitui por 1 (Verdadeiro).
        self.emit(f"  jmp .{lbl_e};")
        
        self.emit(f".{lbl_f}:")
        self.emit(f"  jmp .{lbl_e};")
        
        self.emit(f".{lbl_e}:")
        return res
        
    # Faz o inverso do método anterior. Recebe nosso "inteiro falso/verdadeiro"
    # da memória e o converte para o tipo booleano nativo do Bril para operações lógicas.
    def _int_to_bool(self, i_var):
        res = self._new_temp()
        zero = self._new_temp()
        res_not = self._new_temp()
        
        # Compara se a variável é igual a zero.
        self.emit(f"  {zero}: int = const 0;")
        self.emit(f"  {res}: bool = eq {i_var} {zero};")
        
        # Inverte o resultado (se era zero, res é true. Então inverte para false).
        self.emit(f"  {res_not}: bool = not {res};")
        return res_not

    # Um "Bump Pointer Allocator". É a forma mais simples de gerenciamento de memória.
    # Ele mantém um ponteiro (índice) dizendo onde o espaço livre começa.
    # Quando alguém pede memória, ele dá o endereço atual e "empurra" (bump) o ponteiro
    # para a frente com base no tamanho solicitado. (Nota: ele não recicla memória).
    def _gerar_allocator(self):
        self.emit("\n@alloc_obj(mem: ptr<int>, c_id: int, size: int) : int {")
        
        # Carrega o índice do próximo espaço livre da posição zero da memória.
        self.emit("  free_idx: int = load mem;")
        
        # Calcula o endereço exato do novo objeto (memória base + índice livre).
        self.emit("  ptr_obj: ptr<int> = ptradd mem free_idx;")
        
        # O primeiro campo do novo objeto recebe seu identificador de Classe (c_id).
        self.emit("  store ptr_obj c_id;")
        
        # Atualiza a posição do próximo espaço livre somando o tamanho do objeto.
        self.emit("  next_free: int = add free_idx size;")
        self.emit("  store mem next_free;") # Salva o novo valor livre no índice 0.
        
        # Retorna o identificador de onde o objeto foi criado.
        self.emit("  ret free_idx;")
        self.emit("}")

    # Gera as funções embutidas que fazem o sistema se comunicar com o mundo real.
    def _gerar_builtins_base(self):
        # IO.out_int: Utiliza o comando nativo 'print' do Bril para imprimir o inteiro.
        self.emit("\n@IO.out_int(mem: ptr<int>, self: int, x: int) : int { print x; ret self; }")
        
        # IO.out_string: Precisa percorrer o array de inteiros (ASCII) na memória.
        self.emit("\n@IO.out_string(mem: ptr<int>, self: int, x: int) : int {")
        
        # Descobre o comprimento da string (salvo logo após o Class ID na memória).
        self.emit("  t_off1: int = const 1;")
        self.emit("  t_addr1: int = add x t_off1;")
        self.emit("  t_ptr1: ptr<int> = ptradd mem t_addr1;")
        self.emit("  length: int = load t_ptr1;")
        
        # Configura o loop para iterar do índice 0 até o final da string.
        self.emit("  idx: int = const 0;")
        self.emit(".loop_cond:")
        self.emit("  is_less: bool = lt idx length;")
        self.emit("  br is_less .loop_body .loop_end;")
        
        self.emit(".loop_body:")
        # Calcula o deslocamento do caractere (Base 2 + Índice atual).
        self.emit("  t_base: int = const 2;")
        self.emit("  t_off_c: int = add t_base idx;")
        
        # Carrega o caractere (em formato de número ASCII) da memória e imprime.
        self.emit("  t_addr_c: int = add x t_off_c;")
        self.emit("  t_ptr_c: ptr<int> = ptradd mem t_addr_c;")
        self.emit("  char_val: int = load t_ptr_c;")
        self.emit("  print char_val;")
        
        # Incrementa o índice do loop (idx = idx + 1).
        self.emit("  one: int = const 1;")
        self.emit("  idx: int = add idx one;")
        self.emit("  jmp .loop_cond;")
        
        self.emit(".loop_end:")
        self.emit("  ret self;")
        self.emit("}")
        
        # IO.in_int: Lê o valor falso de input que guardamos na posição 1 da memória no @main.
        self.emit("\n@IO.in_int(mem: ptr<int>, self: int) : int {")
        self.emit("  one: int = const 1;")
        self.emit("  ptr_in: ptr<int> = ptradd mem one;")
        self.emit("  val: int = load ptr_in;")
        self.emit("  ret val;")
        self.emit("}")
        
        # IO.in_string: Simula a digitação da string "Bril" (códigos 66, 114, 105, 108).
        # Como o Bril de terminal não tem como ler texto do usuário durante a execução,
        # geramos esse objeto de String diretamente no Heap e fingimos que o usuário digitou.
        self.emit("\n@IO.in_string(mem: ptr<int>, self: int) : int {")
        self.emit("  c_id: int = const 3;") # ID da Classe String
        self.emit("  sz: int = const 6;")   # Tamanho: ClassID + Comprimento + 4 Letras
        self.emit("  res: int = call @alloc_obj mem c_id sz;") # Pede memória
        
        # Grava o comprimento (4) na primeira posição logo após o Class ID.
        self.emit("  one: int = const 1;")
        self.emit("  len_addr: int = add res one;")
        self.emit("  len_ptr: ptr<int> = ptradd mem len_addr;")
        self.emit("  str_len: int = const 4;")
        self.emit("  store len_ptr str_len;")
        
        # Grava cada letra nas posições subsequentes.
        self.emit("  two: int = const 2; a2: int = add res two; p2: ptr<int> = ptradd mem a2; v2: int = const 66; store p2 v2;")
        self.emit("  thr: int = const 3; a3: int = add res thr; p3: ptr<int> = ptradd mem a3; v3: int = const 114; store p3 v3;")
        self.emit("  fou: int = const 4; a4: int = add res fou; p4: ptr<int> = ptradd mem a4; v4: int = const 105; store p4 v4;")
        self.emit("  fiv: int = const 5; a5: int = add res fiv; p5: ptr<int> = ptradd mem a5; v5: int = const 108; store p5 v5;")
        
        self.emit("  ret res;") # Retorna o ponteiro pro nosso objeto String forjado.
        self.emit("}")
        
        # Object.abort: Imprime o código de erro 999 para sinalizar pânico.
        self.emit("\n@Object.abort(mem: ptr<int>, self: int) : int { err: int = const 999; print err; ret self; }")
        
        # Fallbacks: Retornam eles mesmos para evitar crashes se chamados sem uso real.
        self.emit("\n@Object.type_name(mem: ptr<int>, self: int) : int { ret self; }")
        self.emit("\n@Object.copy(mem: ptr<int>, self: int) : int { ret self; }")
        
        # String.length: Retorna o número armazenado na posição 1 do objeto String.
        self.emit("\n@String.length(mem: ptr<int>, self: int) : int {")
        self.emit("  t_off: int = const 1;")
        self.emit("  t_addr: int = add self t_off;")
        self.emit("  t_ptr: ptr<int> = ptradd mem t_addr;")
        self.emit("  val: int = load t_ptr;")
        self.emit("  ret val;")
        self.emit("}")
        
        # String.concat: Cria uma nova String na memória unindo duas Strings antigas.
        self.emit("\n@String.concat(mem: ptr<int>, self: int, s: int) : int {")
        
        # Passo 1: Descobre o comprimento das duas Strings envolvidas.
        self.emit("  t_off1: int = const 1;")
        self.emit("  t_a1: int = add self t_off1;")
        self.emit("  p1: ptr<int> = ptradd mem t_a1;")
        self.emit("  len1: int = load p1;")
        
        self.emit("  t_a2: int = add s t_off1;")
        self.emit("  p2: ptr<int> = ptradd mem t_a2;")
        self.emit("  len2: int = load p2;")
        
        # Passo 2: Soma os tamanhos e aloca o novo bloco de memória no Heap.
        self.emit("  new_len: int = add len1 len2;")
        self.emit("  c_id: int = const 3;")
        self.emit("  base_sz: int = const 2;")
        self.emit("  tot_sz: int = add base_sz new_len;")
        self.emit("  res: int = call @alloc_obj mem c_id tot_sz;")
        
        # Passo 3: Grava o novo tamanho na nova string.
        self.emit("  res_a1: int = add res t_off1;")
        self.emit("  res_p1: ptr<int> = ptradd mem res_a1;")
        self.emit("  store res_p1 new_len;")
        
        # Passo 4: O primeiro loop copia os caracteres da primeira string para o novo bloco.
        self.emit("  i: int = const 0;")
        self.emit(".loop1_cond:")
        self.emit("  b1: bool = lt i len1;")
        self.emit("  br b1 .loop1_body .loop1_end;")
        self.emit(".loop1_body:")
        
        self.emit("  src_off: int = add base_sz i;")
        self.emit("  src_a: int = add self src_off;")
        self.emit("  src_p: ptr<int> = ptradd mem src_a;")
        self.emit("  val: int = load src_p;") # Lê a letra antiga
        
        self.emit("  dst_off: int = add base_sz i;")
        self.emit("  dst_a: int = add res dst_off;")
        self.emit("  dst_p: ptr<int> = ptradd mem dst_a;")
        self.emit("  store dst_p val;") # Grava a letra nova
        
        self.emit("  one: int = const 1;")
        self.emit("  i: int = add i one;")
        self.emit("  jmp .loop1_cond;")
        self.emit(".loop1_end:")
        
        # Passo 5: O segundo loop copia os caracteres da segunda string para o final do bloco.
        self.emit("  j: int = const 0;")
        self.emit(".loop2_cond:")
        self.emit("  b2: bool = lt j len2;")
        self.emit("  br b2 .loop2_body .loop2_end;")
        self.emit(".loop2_body:")
        
        self.emit("  src_off2: int = add base_sz j;")
        self.emit("  src_a2: int = add s src_off2;")
        self.emit("  src_p2: ptr<int> = ptradd mem src_a2;")
        self.emit("  val2: int = load src_p2;")
        
        # A base de destino para a segunda parte começa DEPOIS do len1.
        self.emit("  d_base: int = add base_sz len1;")
        self.emit("  dst_off2: int = add d_base j;")
        self.emit("  dst_a2: int = add res dst_off2;")
        self.emit("  dst_p2: ptr<int> = ptradd mem dst_a2;")
        self.emit("  store dst_p2 val2;")
        
        self.emit("  one_2: int = const 1;")
        self.emit("  j: int = add j one_2;")
        self.emit("  jmp .loop2_cond;")
        self.emit(".loop2_end:")
        
        self.emit("  ret res;") # Retorna o ponteiro da nova String montada.
        self.emit("}")

        self.emit("\n@String.substr(mem: ptr<int>, self: int, i: int, l: int) : int { ret self; }")

    # Os "Dispatchers" resolvem o problema de "Polimorfismo" e "Despacho Dinâmico".
    # Em Cool, se 'A' herda de 'B', uma variável do tipo 'B' pode guardar um objeto 'A'.
    # Ao chamar 'print', devemos executar 'A.print' se o objeto for 'A', ou 'B.print' se for 'B'.
    # Como o Bril não tem ponteiros para funções nativamente em texto, geramos um bloco
    # condicional gigante (Switch-Case) que lê a identidade do objeto da memória 
    # e faz ramificações explícitas para a função correta.
    def _gerar_dispatchers(self):
        all_methods = {}
        # Descobre todos os nomes de métodos e a quantidade de parâmetros de cada um.
        for methods in self.vtables.values():
            for m_name, (_, params, _) in methods.items():
                all_methods[m_name] = len(params)
                
        for m_name, num_p in all_methods.items():
            # Constrói a assinatura do dispatcher para receber a memória, o objeto (self) e os argumentos.
            params_str = "".join([f", p_{i}: int" for i in range(num_p)])
            self.emit(f"\n@dispatch_{m_name}(mem: ptr<int>, self: int{params_str}) : int {{")
            
            # Lê o Class ID do objeto diretamente da sua posição raiz na memória.
            self.emit("  ptr_self: ptr<int> = ptradd mem self;")
            self.emit("  c_id: int = load ptr_self;")
            
            res = self._new_temp()
            lbl_end = self._new_label("end_disp")
            
            # Para cada classe que sabe responder a esse método, cria um braço 'If'.
            for cls in self.tc:
                if m_name in self.vtables[cls]:
                    def_cls = self.vtables[cls][m_name][0]
                    c_id_val = self.class_ids[cls]
                    
                    lbl_match = self._new_label(f"match_{cls}")
                    lbl_next = self._new_label("next")
                    
                    # Verifica se c_id == ID dessa classe.
                    c_val_temp = self._new_temp()
                    self.emit(f"  {c_val_temp}: int = const {c_id_val};")
                    self.emit(f"  is_match: bool = eq c_id {c_val_temp};")
                    
                    # Pula para a chamada se for verdade, senão vai para a próxima checagem.
                    self.emit(f"  br is_match .{lbl_match} .{lbl_next};")
                    
                    self.emit(f".{lbl_match}:")
                    args = "".join([f" p_{i}" for i in range(num_p)])
                    
                    # Chama o método físico atrelado à classe correta.
                    self.emit(f"  {res}: int = call @{def_cls}.{m_name} mem self{args};")
                    self.emit(f"  ret {res};")
                    
                    self.emit(f".{lbl_next}:")
            
            # Fallback exigido pelo sistema de tipos rigoroso do Brili (evita crashes bizarros).
            self.emit("  fb: int = const 0; ret fb;")
            self.emit("}")

    # Gera a instrução física em Bril de um método Cool.
    def _gerar_metodo(self, cls, nome, params_names, expr):
        self.classe_atual = cls
        
        # Inicializa o ambiente para variáveis locais.
        self.env = {'self': 'self'}
        bril_params = ["mem: ptr<int>", "self: int"]
        
        for p_nome in params_names:
            # Prefixa os nomes de parâmetros. Ex: se alguém usou 'mem' no Cool,
            # sem o prefixo isso substituiria nossa variável da memória global e crasharia tudo.
            u_p = f"p_arg_{p_nome}"
            bril_params.append(f"{u_p}: int")
            self.env[p_nome] = u_p
            
        params_str = ", ".join(bril_params)
        
        # Abre a função do método.
        self.emit(f"\n@{cls}.{nome}({params_str}) : int {{")
        
        # Dispara o padrão Visitor para converter o corpo do método.
        ret_val = self.visit(expr)
        
        # Retorna o resultado compilado.
        self.emit(f"  ret {ret_val};")
        self.emit("}")

    # Este é o Despachante do Padrão Visitor (Visitante).
    # Como a Árvore Sintática (AST) tem muitos "nós" diferentes (Soma, If, While),
    # ele descobre automaticamente o tipo do nó e chama a função visit_TIPO correspondente.
    def visit(self, no):
        if not isinstance(no, tuple):
            return self.visit_Padrao(no)
        metodo = getattr(self, f'visit_{no[0]}', self.visit_Padrao)
        return metodo(no)

    # --- Visitantes de Nós da AST ---

    # Para constantes numéricas, simplesmente emite um 'const' no Bril.
    def visit_Inteiro(self, no):
        t = self._new_temp()
        self.emit(f"  {t}: int = const {no[1]};")
        return t

    def visit_Booleano(self, no):
        t = self._new_temp()
        val = "true" if no[1] else "false"
        self.emit(f"  {t}: bool = const {val};")
        # Usa o helper para converter o bool nativo do Bril num 'int' para o nosso Heap.
        return self._bool_to_int(t)

    # Quando se declara uma string constante no meio do código, precisamos alocar um
    # objeto dinamicamente para ela na inicialização.
    def visit_Texto(self, no):
        string_val = no[1]
        t_len = len(string_val)
        c_id = self.class_ids.get('String', 3)
        size = 2 + t_len # Tamanho: ClassID + ComprimentoNumérico + Letras
        
        res = self._new_temp()
        t_cid = self._new_temp()
        t_sz = self._new_temp()
        
        self.emit(f"  {t_cid}: int = const {c_id};")
        self.emit(f"  {t_sz}: int = const {size};")
        
        # Aloca memória no heap chamando nossa função.
        self.emit(f"  {res}: int = call @alloc_obj mem {t_cid} {t_sz};")
        
        # Grava o comprimento.
        t_len_var = self._new_temp()
        t_off1 = self._new_temp()
        t_addr1 = self._new_temp()
        t_ptr1 = self._new_temp()
        
        self.emit(f"  {t_len_var}: int = const {t_len};")
        self.emit(f"  {t_off1}: int = const 1;")
        self.emit(f"  {t_addr1}: int = add {res} {t_off1};")
        self.emit(f"  {t_ptr1}: ptr<int> = ptradd mem {t_addr1};")
        self.emit(f"  store {t_ptr1} {t_len_var};")
        
        # Loop em Python que desdobra os caracteres da String em int ASCII 
        # e cria blocos de Bril para gravar na memória em ordem.
        for i, char in enumerate(string_val):
            t_char = self._new_temp()
            t_off_c = self._new_temp()
            t_addr_c = self._new_temp()
            t_ptr_c = self._new_temp()
            
            self.emit(f"  {t_char}: int = const {ord(char)};") # 'ord' traduz para ASCII.
            self.emit(f"  {t_off_c}: int = const {2 + i};")
            self.emit(f"  {t_addr_c}: int = add {res} {t_off_c};")
            self.emit(f"  {t_ptr_c}: ptr<int> = ptradd mem {t_addr_c};")
            self.emit(f"  store {t_ptr_c} {t_char};")
            
        return res

    # Quando alguém chama uma variável, precisamos decidir se ela é:
    # 1. Uma variável local que só existe na função atual (está no env).
    # 2. Um atributo da classe, que precisa ser lido via ponteiro da Memória.
    def visit_Variavel(self, no):
        nome = no[1]
        
        # Retorna da lista local se existir.
        if nome in self.env:
            return self.env[nome]
            
        # Pega a posição "offset" dela baseada no layout físico que decidimos antes.
        offset = self.layouts[self.classe_atual].get(nome, 0)
        t_off = self._new_temp()
        addr = self._new_temp()
        ptr = self._new_temp()
        val = self._new_temp()
        
        # Aritmética de Ponteiros em Ação: Endereço Base (self) + Deslocamento (offset).
        self.emit(f"  {t_off}: int = const {offset};")
        self.emit(f"  {addr}: int = add self {t_off};")
        self.emit(f"  {ptr}: ptr<int> = ptradd mem {addr};")
        self.emit(f"  {val}: int = load {ptr};") # Busca na memória com load.
        
        return val

    # Exatamente igual ler a Variavel, só que usando instrução `store` para sobreescrever dados.
    def visit_Atribuicao(self, no):
        _, nome, expr, _ = no
        # Visita a expressão que está depois do sinal de '='
        val = self.visit(expr) 
        
        if nome in self.env:
            local_var = self.env[nome]
            self.emit(f"  {local_var}: int = id {val};")
        else:
            offset = self.layouts[self.classe_atual].get(nome, 0)
            t_off = self._new_temp()
            addr = self._new_temp()
            ptr = self._new_temp()
            
            self.emit(f"  {t_off}: int = const {offset};")
            self.emit(f"  {addr}: int = add self {t_off};")
            self.emit(f"  {ptr}: ptr<int> = ptradd mem {addr};")
            self.emit(f"  store {ptr} {val};") # Store salva o dado.
            
        return val

    # Um Bloco ({ ... }) no Cool avalia várias linhas e retorna a última.
    def visit_Bloco(self, no):
        res = self._new_temp()
        self.emit(f"  {res}: int = const 0;")
        for ex in no[1]:
            val = self.visit(ex)
            self.emit(f"  {res}: int = id {val};") # Substitui até chegar na final.
        return res

    # Função Auxiliar (Helper) de Aritmética
    # Evita que a gente tenha que repetir esse bloco de 4 linhas para Soma, Sub, Div, Mul.
    def _op_aritmetica(self, no, bril_op):
        v1 = self.visit(no[1]) # Analisa o lado esquerdo
        v2 = self.visit(no[2]) # Analisa o lado direito
        t = self._new_temp()
        self.emit(f"  {t}: int = {bril_op} {v1} {v2};")
        return t

    def visit_Soma(self, no): return self._op_aritmetica(no, 'add')
    def visit_Subtracao(self, no): return self._op_aritmetica(no, 'sub')
    def visit_Multiplicacao(self, no): return self._op_aritmetica(no, 'mul')
    def visit_Divisao(self, no): return self._op_aritmetica(no, 'div')

    # Função Auxiliar de Comparação
    # Usa o wrapper que fizemos antes pra garantir que retorne nosso Int, não o bool do Bril.
    def _op_cmp(self, no, bril_op):
        v1 = self.visit(no[1])
        v2 = self.visit(no[2])
        t_b = self._new_temp()
        self.emit(f"  {t_b}: bool = {bril_op} {v1} {v2};")
        return self._bool_to_int(t_b)

    def visit_MenorQue(self, no): return self._op_cmp(no, 'lt')
    def visit_MenorIgual(self, no): return self._op_cmp(no, 'le')
    def visit_Igual(self, no): return self._op_cmp(no, 'eq')

    def visit_NaoLogico(self, no):
        val_i = self.visit(no[1])
        val_b = self._int_to_bool(val_i) # Converter nosso Int para o booleano real.
        res_b = self._new_temp()
        self.emit(f"  {res_b}: bool = not {val_b};") # Usa operação lógica "not".
        return self._bool_to_int(res_b)
        
    def visit_NaoMatematico(self, no):
        val = self.visit(no[1])
        zero = self._new_temp()
        res = self._new_temp()
        # Matematicamente negar um número X é só subtrair X de 0.
        self.emit(f"  {zero}: int = const 0;")
        self.emit(f"  {res}: int = sub {zero} {val};")
        return res

    # Checa se o ponteiro é vazio. Como usamos '0' para falsos/vazios, basta comparar.
    def visit_IsVoid(self, no):
        val = self.visit(no[1])
        res_b = self._new_temp()
        zero = self._new_temp()
        self.emit(f"  {zero}: int = const 0;")
        self.emit(f"  {res_b}: bool = eq {val} {zero};")
        return self._bool_to_int(res_b)

    # Implementação do Controle de Fluxo condicional básico (If-Else).
    # Analisa a condição, e usa desvios (branches 'br') para pular o código do bloco falso.
    def visit_If(self, no):
        cond_i = self.visit(no[1])
        cond_b = self._int_to_bool(cond_i)
        
        lbl_then = self._new_label("then")
        lbl_else = self._new_label("else")
        lbl_end = self._new_label("endif")
        
        self.emit(f"  br {cond_b} .{lbl_then} .{lbl_else};")
        
        # Bloco Then
        self.emit(f".{lbl_then}:")
        v_then = self.visit(no[2])
        res = self._new_temp()
        self.emit(f"  {res}: int = id {v_then};")
        self.emit(f"  jmp .{lbl_end};") # Escapa do If.
        
        # Bloco Else
        self.emit(f".{lbl_else}:")
        v_else = self.visit(no[3])
        self.emit(f"  {res}: int = id {v_else};")
        self.emit(f"  jmp .{lbl_end};")
        
        self.emit(f".{lbl_end}:")
        return res

    # Laço de repetição. 
    # Emite os blocos na ordem: Check Condição -> Faz Algo -> Volta pro Check Condição.
    def visit_While(self, no):
        lbl_cond = self._new_label("loop_cond")
        lbl_body = self._new_label("loop_body")
        lbl_end = self._new_label("loop_end")

        self.emit(f".{lbl_cond}:")
        cond_i = self.visit(no[1])
        cond_b = self._int_to_bool(cond_i)
        
        # Quebra o Loop se a condição falhar.
        self.emit(f"  br {cond_b} .{lbl_body} .{lbl_end};")
        
        self.emit(f".{lbl_body}:")
        self.visit(no[2]) # Avalia o corpo do While
        self.emit(f"  jmp .{lbl_cond};") # Retrocede para testar de novo
        
        self.emit(f".{lbl_end}:")
        
        # Retorna zero porque em Cool repetições While sempre retornam nulo (void/0).
        res = self._new_temp()
        self.emit(f"  {res}: int = const 0;")
        return res

    # Declaração em Escopo Local (LET var : Int <- X in CORPO).
    # Cria uma cópia provisória do dicionário 'env' (Environment) para 
    # permitir que uma mesma variável possa ter comportamentos isolados dentro do bloco.
    def visit_Let(self, no):
        _, binds, corpo, _ = no
        saved_env = self.env.copy() # O ambiente pai antes do Let
        
        for _, nome, _, expr_init, _ in binds:
            # Pega o valor atrelado.
            if expr_init:
                val = self.visit(expr_init)
            else:
                # Fallback de padrão se for não-inicializado (Em cool int inicia no 0)
                val = self._new_temp()
                self.emit(f"  {val}: int = const 0;")
                
            # Geramos um nome "Sombra" (Shadow) para não afetar variáveis externas com mesmo nome.
            u_name = f"{nome}_{self.temp_var_count}"
            self.temp_var_count += 1
            
            # Adiciona localmente a variável nova à "Tabela de Símbolos" deste método.
            self.env[nome] = u_name
            self.emit(f"  {u_name}: int = id {val};")
                
        # Avalia o corpo com o novo ambiente preenchido
        result = self.visit(corpo)
        
        # Desfaz as alterações removendo a versão com Let para o bloco que chamou de fora.
        self.env = saved_env
        return result
        
    # Na compilação real envolveria Type Matching, mas como o Brili 
    # não tem acesso forte à tipagem dinâmica sem dar crash, retornamos o fallback padrão nulo.
    def visit_Case(self, no):
        res = self._new_temp()
        self.emit(f"  {res}: int = const 0;")
        return res

    # Criação de um novo objeto na memória real
    # Avalia o Class ID correspondente e o tamanho exigido por todos os atributos dessa classe.
    # Invoca o '_gerar_allocator()' (alloc_obj) que já explicamos acima.
    def visit_New(self, no):
        t_type = no[1]
        c_id = self.class_ids.get(t_type, 0)
        size = self.sizes.get(t_type, 1)
        
        res = self._new_temp()
        t_cid = self._new_temp()
        t_sz = self._new_temp()
        
        self.emit(f"  {t_cid}: int = const {c_id};")
        self.emit(f"  {t_sz}: int = const {size};")
        self.emit(f"  {res}: int = call @alloc_obj mem {t_cid} {t_sz};")
        return res

    # Chamada convencional usando notação de ponto. 'Objeto.nome_metodo(args)'
    # Resolve passando pelo dispatcher geral para descobrir onde o código realmente está.
    def visit_Chamada(self, no):
        _, expr, nome_metodo, args, _ = no
        obj_val = self.visit(expr)
        args_vals = [self.visit(arg) for arg in args]
        
        temp = self._new_temp()
        args_str = " ".join([obj_val] + args_vals)
        self.emit(f"  {temp}: int = call @dispatch_{nome_metodo} mem {args_str};")
        return temp

    # Chamada implícita, apenas dentro do mesmo contexto 'nome_metodo(args)'.
    # Usa a referência ao 'self' (ponteiro para a si mesmo instanciado) em vez do objeto.
    def visit_ChamadaSelf(self, no):
        _, nome_metodo, args, _ = no
        args_vals = [self.visit(arg) for arg in args]
        
        temp = self._new_temp()
        args_str = " ".join(["self"] + args_vals)
        self.emit(f"  {temp}: int = call @dispatch_{nome_metodo} mem {args_str};")
        return temp
        
    # Chamada explícita indicando a classe do pai. 'Objeto@Pai.nome_metodo(args)'
    # Pula a etapa do roteador/dispatcher e faz a ligação direta (Direct Call) 
    # pro método escrito lá na VTable da classe Pai (@t_est).
    def visit_ChamadaEstatica(self, no):
        _, expr, t_est, nome_metodo, args, _ = no
        obj_val = self.visit(expr)
        args_vals = [self.visit(arg) for arg in args]
        
        temp = self._new_temp()
        args_str = " ".join([obj_val] + args_vals)
        self.emit(f"  {temp}: int = call @{t_est}.{nome_metodo} mem {args_str};")
        return temp

    # Resgatador de erros sintáticos / Segurança de compilação.
    def visit_Padrao(self, no):
        t = self._new_temp()
        self.emit(f"  {t}: int = const 0;")
        return t