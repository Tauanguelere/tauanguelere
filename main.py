from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
from datetime import date
import psycopg2
from psycopg2 import extras # Para usar RealDictCursor
import traceback # Importa para rastreamento de erros

app = Flask(__name__)
CORS(app) # Habilita CORS para todas as rotas

# Configurações do banco de dados PostgreSQL
# ATENÇÃO: Substitua 'seu_banco_de_dados', 'seu_usuario' e 'sua_senha' pelas suas credenciais reais
DB_HOST = "localhost"
DB_NAME = "teste01"
DB_USER = "admin"
DB_PASS = "123"

# Define a ordem fixa das colunas para garantir a inserção/atualização correta
COFFEE_LOT_COLUMNS = [
    "id", "lote_numero", "balanca", "caminhoneiro", "data_entrada",
    "qtd_lotes_veiculo", "boca_entrada", "situacao_cafe_veiculo", "safra",
    "nome_produtor", "nome_propriedade", "endereco", "telefone",
    "tipo_servico", "qtd_sacas", "peso_total_sacas_kg", "peso_total_bag_kg",
    "qtd_bags", "divisao_bags_kg", "peso_entrada_caminhao_kg", "fair_trade",
    "empresa", "status"
]

def get_db_connection():
    """Estabelece uma conexão com o banco de dados PostgreSQL."""
    conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
    return conn

def create_table_if_not_exists():
    """Cria a tabela 'coffee_lots' se ela ainda não existir."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS coffee_lots (
                id VARCHAR(255) PRIMARY KEY,
                lote_numero VARCHAR(255),
                balanca VARCHAR(255),
                caminhoneiro VARCHAR(255),
                data_entrada DATE,
                qtd_lotes_veiculo INTEGER,
                boca_entrada INTEGER,
                situacao_cafe_veiculo VARCHAR(255),
                safra VARCHAR(255),
                nome_produtor VARCHAR(255),
                nome_propriedade VARCHAR(255),
                endereco VARCHAR(255),
                telefone VARCHAR(255),
                tipo_servico VARCHAR(255),
                qtd_sacas INTEGER,
                peso_total_sacas_kg DOUBLE PRECISION,
                peso_total_bag_kg DOUBLE PRECISION,
                qtd_bags INTEGER,
                divisao_bags_kg DOUBLE PRECISION,
                peso_entrada_caminhao_kg DOUBLE PRECISION,
                fair_trade VARCHAR(255),
                empresa VARCHAR(255),
                status VARCHAR(50) DEFAULT 'active'
            );
        """)
        conn.commit()
        cur.close()
        print("Tabela 'coffee_lots' verificada/criada com sucesso.")
    except Exception as e:
        print(f"Erro ao criar tabela 'coffee_lots': {e}")
        traceback.print_exc() # Imprime o rastreamento completo do erro
    finally:
        if conn:
            conn.close()

def create_producers_table_if_not_exists():
    """
    Cria a tabela 'producers' se ela ainda não existir e garante a extensão uuid-ossp
    e a coluna property_name. Adiciona um índice único funcional para normalização.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Primeiro, cria a extensão uuid-ossp se ela não existir
        cur.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
        conn.commit() # Commit para garantir que a extensão esteja disponível antes de usá-la

        # Cria a tabela 'producers' se ela ainda não existir
        cur.execute("""
            CREATE TABLE IF NOT EXISTS producers (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), -- Usando uuid_generate_v4() da extensão
                name VARCHAR(255) NOT NULL,
                property_name VARCHAR(255) -- Coluna para o nome da propriedade
            );
        """)
        conn.commit()

        # Verifica se a coluna 'property_name' existe e a adiciona se não existir
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'producers' AND column_name = 'property_name';
        """)
        column_exists = cur.fetchone()
        if not column_exists:
            cur.execute("ALTER TABLE producers ADD COLUMN property_name VARCHAR(255);")
            conn.commit()
            print("Coluna 'property_name' adicionada à tabela 'producers'.")

        # Adiciona um índice único funcional para garantir a unicidade de nomes e propriedades normalizados
        # Primeiro, remove restrições UNIQUE antigas que possam conflitar
        cur.execute("""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'producers_name_key' AND contype = 'u') THEN
                    ALTER TABLE producers DROP CONSTRAINT producers_name_key;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unique_producer_name_property' AND contype = 'u') THEN
                    ALTER TABLE producers DROP CONSTRAINT unique_producer_name_property;
                END IF;
            END
            $$;
        """)
        conn.commit()
        
        # Cria o índice único funcional
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_normalized_producer
            ON producers (TRIM(LOWER(name)), TRIM(LOWER(property_name)));
        """)
        conn.commit()


        cur.close()
        print("Tabela 'producers' verificada/criada com sucesso com índice normalizado.")
    except Exception as e:
        print(f"Erro ao criar tabela 'producers' ou extensão uuid-ossp/índice: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

# NOVO: Função para criar a tabela 'drivers'
def create_drivers_table_if_not_exists():
    """
    Cria a tabela 'drivers' se ela ainda não existir.
    Adiciona um índice único funcional para normalização do nome do caminhoneiro.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS drivers (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                name VARCHAR(255) NOT NULL
            );
        """)
        conn.commit()

        # Adiciona um índice único funcional para garantir a unicidade de nomes de caminhoneiros normalizados
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_normalized_driver
            ON drivers (TRIM(LOWER(name)));
        """)
        conn.commit()

        cur.close()
        print("Tabela 'drivers' verificada/criada com sucesso com índice normalizado.")
    except Exception as e:
        print(f"Erro ao criar tabela 'drivers' ou índice: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

def add_producer_if_not_exists(producer_name, property_name=""):
    """Adiciona um nome de produtor e sua propriedade à tabela 'producers' se ele não existir."""
    if not producer_name or producer_name.strip() == '':
        return

    # Normaliza os valores para inserção e comparação
    normalized_producer_name = producer_name.strip()
    normalized_property_name = property_name.strip() if property_name is not None else ""

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Tenta inserir o nome do produtor e a propriedade.
        # Usa ON CONFLICT (TRIM(LOWER(name)), TRIM(LOWER(property_name))) DO NOTHING
        # para usar o índice funcional e evitar duplicatas normalizadas.
        cur.execute(
            "INSERT INTO producers (name, property_name) VALUES (%s, %s) "
            "ON CONFLICT (TRIM(LOWER(name)), TRIM(LOWER(property_name))) DO NOTHING;",
            (normalized_producer_name, normalized_property_name)
        )
        conn.commit()
        cur.close()
        print(f"Produtor '{normalized_producer_name}' com propriedade '{normalized_property_name}' verificado/adicionado/atualizado na tabela 'producers'.")
    except Exception as e:
        print(f"Erro ao adicionar/atualizar produtor '{normalized_producer_name}' à tabela 'producers': {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

# NOVO: Função para adicionar caminhoneiro se não existir
def add_driver_if_not_exists(driver_name):
    """Adiciona um nome de caminhoneiro à tabela 'drivers' se ele não existir."""
    if not driver_name or driver_name.strip() == '':
        return

    normalized_driver_name = driver_name.strip()

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO drivers (name) VALUES (%s) "
            "ON CONFLICT (TRIM(LOWER(name))) DO NOTHING;",
            (normalized_driver_name,)
        )
        conn.commit()
        cur.close()
        print(f"Caminhoneiro '{normalized_driver_name}' verificado/adicionado na tabela 'drivers'.")
    except Exception as e:
        print(f"Erro ao adicionar/atualizar caminhoneiro '{normalized_driver_name}' à tabela 'drivers': {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

# Garante que as tabelas sejam criadas ao iniciar a aplicação
with app.app_context():
    create_table_if_not_exists()
    create_producers_table_if_not_exists()
    create_drivers_table_if_not_exists() # NOVO: Cria a tabela de caminhoneiros


def serialize_coffee_lot(lot):
    """
    Converte um registro de lote de café (geralmente um RealDictRow) em um dicionário
    e serializa objetos de data para strings ISO 8601.
    """
    lot_dict = dict(lot) # Converte RealDictRow para dict
    if isinstance(lot_dict.get('data_entrada'), date):
        lot_dict['data_entrada'] = lot_dict['data_entrada'].isoformat()
    return lot_dict

def validate_boca_entrada(boca_num, current_lot_id=None):
    """
    Valida o número da boca de entrada, verificando se está entre 1 e 8
    e se já está em uso por outro lote ativo.
    """
    if boca_num is None or not (1 <= boca_num <= 8):
        return {"isValid": False, "message": "Nº da Boca de Entrada deve ser entre 1 e 8."}

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        query = "SELECT id FROM coffee_lots WHERE status = 'active' AND boca_entrada = %s"
        params = [boca_num]
        
        if current_lot_id:
            query += " AND id != %s"
            params.append(current_lot_id)
        
        cur.execute(query, params)
        is_boca_taken = cur.fetchone() is not None
        cur.close()
        
        if is_boca_taken:
            return {"isValid": False, "message": f"Nº da Boca de Entrada {boca_num} já está em uso por um lote ativo."}
    except Exception as e:
        print(f"Erro ao validar boca de entrada: {e}")
        traceback.print_exc() # Imprime o rastreamento completo do erro
        return {"isValid": False, "message": "Erro interno ao validar boca de entrada."}
    finally:
        if conn:
            conn.close()

    return {"isValid": True, "message": ""}

@app.route('/api/coffee-lots', methods=['GET'])
def get_all_coffee_lots():
    """Retorna todos os lotes de café do banco de dados."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) # Retorna dicionários
        cur.execute("SELECT * FROM coffee_lots")
        lots = cur.fetchall()
        cur.close()
        return jsonify([serialize_coffee_lot(lot) for lot in lots])
    except Exception as e:
        print(f"Erro ao buscar lotes: {e}")
        traceback.print_exc() # Imprime o rastreamento completo do erro
        return jsonify({"message": "Erro interno do servidor ao buscar lotes."}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/coffee-lots/<string:lot_id>', methods=['GET'])
def get_coffee_lot_by_id(lot_id):
    """Retorna um lote de café específico por ID."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM coffee_lots WHERE id = %s", (lot_id,))
        lot = cur.fetchone()
        cur.close()
        if lot:
            return jsonify(serialize_coffee_lot(lot))
        return jsonify({"message": "Lote não encontrado"}), 404
    except Exception as e:
        print(f"Erro ao buscar lote por ID: {e}")
        traceback.print_exc() # Imprime o rastreamento completo do erro
        return jsonify({"message": "Erro interno do servidor ao buscar lote."}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/coffee-lots', methods=['POST'])
def add_coffee_lot():
    """Adiciona um novo lote de café ao banco de dados."""
    new_lot_data = request.get_json()

    boca_entrada = new_lot_data.get('boca_entrada')
    validation_result = validate_boca_entrada(boca_entrada)
    if not validation_result["isValid"]:
        return jsonify({"message": validation_result["message"]}), 400

    if 'data_entrada' in new_lot_data and new_lot_data['data_entrada']:
        try:
            new_lot_data['data_entrada'] = date.fromisoformat(new_lot_data['data_entrada'])
        except ValueError:
            return jsonify({"message": "Formato de data inválido. Use YYYY-MM-DD."}), 400

    new_lot_data['id'] = str(uuid.uuid4())
    new_lot_data['status'] = new_lot_data.get('status', 'active') # Garante status padrão

    # NOVO: Adiciona o nome do produtor e a propriedade à tabela 'producers' se não existir
    producer_name = new_lot_data.get('nome_produtor')
    property_name = new_lot_data.get('nome_propriedade', '') # Pega a propriedade, padrão vazio
    if producer_name:
        add_producer_if_not_exists(producer_name, property_name)

    # NOVO: Adiciona o nome do caminhoneiro à tabela 'drivers' se não existir
    driver_name = new_lot_data.get('caminhoneiro')
    if driver_name:
        add_driver_if_not_exists(driver_name)

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Prepara os dados na ordem correta das colunas
        insert_values = []
        for col in COFFEE_LOT_COLUMNS:
            insert_values.append(new_lot_data.get(col))

        columns_str = ', '.join(COFFEE_LOT_COLUMNS)
        placeholders_str = ', '.join(['%s'] * len(COFFEE_LOT_COLUMNS))
        query = f"INSERT INTO coffee_lots ({columns_str}) VALUES ({placeholders_str})"
        
        cur.execute(query, insert_values) # Usa a lista ordenada de valores
        conn.commit()
        cur.close()
        return jsonify(serialize_coffee_lot(new_lot_data)), 201
    except Exception as e:
        print(f"Erro ao adicionar lote: {e}")
        traceback.print_exc() # Imprime o rastreamento completo do erro
        return jsonify({"message": "Erro interno do servidor ao adicionar lote."}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/coffee-lots/<string:lot_id>', methods=['PUT'])
def update_coffee_lot(lot_id):
    """Atualiza um lote de café existente no banco de dados."""
    updated_data = request.get_json()

    boca_entrada = updated_data.get('boca_entrada')
    validation_result = validate_boca_entrada(boca_entrada, lot_id)
    if not validation_result["isValid"]:
        return jsonify({"message": validation_result["message"]}), 400

    if 'data_entrada' in updated_data and updated_data['data_entrada']:
        try:
            updated_data['data_entrada'] = date.fromisoformat(updated_data['data_entrada'])
        except ValueError:
            return jsonify({"message": "Formato de data inválido. Use YYYY-MM-DD."}), 400

    # NOVO: Adiciona o nome do produtor e a propriedade à tabela 'producers' se não existir
    producer_name = updated_data.get('nome_produtor')
    property_name = updated_data.get('nome_propriedade', '') # Pega a propriedade, padrão vazio
    if producer_name:
        add_producer_if_not_exists(producer_name, property_name)

    # NOVO: Adiciona o nome do caminhoneiro à tabela 'drivers' se não existir
    driver_name = updated_data.get('caminhoneiro')
    if driver_name:
        add_driver_if_not_exists(driver_name)

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        set_clauses = []
        params = []
        # Itera sobre as colunas definidas para garantir a ordem e incluir apenas dados presentes
        for col in COFFEE_LOT_COLUMNS:
            if col in updated_data:
                set_clauses.append(f"{col} = %s")
                params.append(updated_data[col])
        
        if not set_clauses: # Nenhuns dados para atualizar
            return jsonify({"message": "Nenhum dado fornecido para atualização."}), 400

        params.append(lot_id) # Adiciona o ID para a cláusula WHERE
        
        query = f"UPDATE coffee_lots SET {', '.join(set_clauses)} WHERE id = %s"
        
        cur.execute(query, params)
        conn.commit()
        
        if cur.rowcount == 0: # Verifica se alguma linha foi atualizada
            cur.close()
            return jsonify({"message": "Lote não encontrado"}), 404
        
        cur.close()
        # Retorna o lote atualizado buscando-o novamente
        return get_coffee_lot_by_id(lot_id) # Reutiliza a função GET para retornar o lote atualizado
    except Exception as e:
        print(f"Erro ao atualizar lote: {e}")
        traceback.print_exc() # Imprime o rastreamento completo do erro
        return jsonify({"message": "Erro interno do servidor ao atualizar lote."}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/coffee-lots/<string:lot_id>', methods=['DELETE'])
def delete_coffee_lot(lot_id):
    """Deleta um lote de café do banco de dados."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM coffee_lots WHERE id = %s", (lot_id,))
        conn.commit()
        if cur.rowcount > 0:
            cur.close()
            return jsonify({"message": "Lote removido com sucesso"}), 204
        cur.close()
        return jsonify({"message": "Lote não encontrado"}), 404
    except Exception as e:
        print(f"Erro ao deletar lote: {e}")
        traceback.print_exc() # Imprime o rastreamento completo do erro
        return jsonify({"message": "Erro interno do servidor ao deletar lote."}), 500
    finally:
        if conn:
            conn.close()

# Endpoint para obter nomes de produtores (agora da tabela 'producers')
@app.route('/api/producers', methods=['GET'])
def get_producer_names():
    """Retorna uma lista de nomes de produtores únicos do banco de dados."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Seleciona nomes de produtores e suas propriedades, ordenando pelo nome
        cur.execute("SELECT id, name, property_name FROM producers ORDER BY name") # Adicionado 'id'
        # Retorna uma lista de dicionários para o frontend
        producers_with_properties = [{"id": str(row[0]), "name": row[1], "property": row[2]} for row in cur.fetchall()] # Mapeia 'id'
        cur.close()
        return jsonify(producers_with_properties)
    except Exception as e:
        print(f"Erro ao buscar nomes de produtores: {e}")
        traceback.print_exc() # Imprime o rastreamento completo do erro
        return jsonify({"message": "Erro interno do servidor ao buscar nomes de produtores."}), 500
    finally:
        if conn:
            conn.close()

# NOVO ENDPOINT: Para adicionar um único produtor
@app.route('/api/producers', methods=['POST'])
def add_single_producer():
    """Adiciona um único produtor ao banco de dados."""
    data = request.get_json()
    producer_name = data.get('name')
    property_name = data.get('property', '')

    print(f"Recebido POST para /api/producers: Nome='{producer_name}', Propriedade='{property_name}'") # Log de depuração

    if not producer_name or producer_name.strip() == '':
        return jsonify({"message": "O nome do produtor não pode ser vazio."}), 400

    # Normaliza os valores para inserção e comparação
    normalized_producer_name = producer_name.strip()
    normalized_property_name = property_name.strip() if property_name is not None else ""

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica se o produtor já existe usando os valores normalizados
        cur.execute("SELECT id FROM producers WHERE TRIM(LOWER(name)) = TRIM(LOWER(%s)) AND TRIM(LOWER(property_name)) = TRIM(LOWER(%s));", (normalized_producer_name, normalized_property_name))
        existing_producer = cur.fetchone()
        if existing_producer:
            cur.close()
            return jsonify({"message": "Produtor com o mesmo nome e propriedade já existe."}), 409 # 409 Conflict

        # Insere o novo produtor com os valores normalizados
        cur.execute("INSERT INTO producers (name, property_name) VALUES (%s, %s) RETURNING id;", (normalized_producer_name, normalized_property_name))
        producer_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        return jsonify({"id": str(producer_id), "name": normalized_producer_name, "property": normalized_property_name}), 201
    except Exception as e:
        print(f"Erro ao adicionar produtor: {e}")
        traceback.print_exc()
        return jsonify({"message": "Erro interno do servidor ao adicionar produtor."}), 500
    finally:
        if conn:
            conn.close()

# NOVO ENDPOINT: Para deletar um produtor
@app.route('/api/producers', methods=['DELETE'])
def delete_producer():
    """Deleta um produtor do banco de dados pelo nome e propriedade."""
    data = request.get_json()
    producer_name = data.get('name')
    property_name = data.get('property', '')

    print(f"Recebido DELETE para /api/producers: Nome='{producer_name}', Propriedade='{property_name}'") # Log de depuração

    if not producer_name or producer_name.strip() == '':
        return jsonify({"message": "O nome do produtor é obrigatório para a exclusão."}), 400

    # Normaliza os valores para comparação
    normalized_producer_name = producer_name.strip()
    normalized_property_name = property_name.strip() if property_name is not None else ""

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Deleta o produtor, usando LOWER() e TRIM() para comparação insensível a maiúsculas/minúsculas e espaços
        cur.execute("DELETE FROM producers WHERE TRIM(LOWER(name)) = TRIM(LOWER(%s)) AND TRIM(LOWER(property_name)) = TRIM(LOWER(%s));", (normalized_producer_name, normalized_property_name))
        conn.commit()
        
        if cur.rowcount > 0:
            cur.close()
            return jsonify({"message": "Produtor removido com sucesso."}), 204 # 204 No Content
        else:
            cur.close()
            return jsonify({"message": "Produtor não encontrado ou já removido."}), 404 # 404 Not Found
    except Exception as e:
        print(f"Erro ao deletar produtor: {e}")
        traceback.print_exc()
        return jsonify({"message": "Erro interno do servidor ao deletar produtor."}), 500
    finally:
        if conn:
            conn.close()


# NOVO ENDPOINT: Para importar uma lista de nomes de produtores com propriedades
@app.route('/api/producers/import', methods=['POST'])
def import_producer_names():
    """Importa uma lista de nomes de produtores (com propriedades) para a base de dados."""
    producers_to_import = request.get_json()

    if not isinstance(producers_to_import, list):
        return jsonify({"message": "O corpo da requisição deve ser uma lista de objetos de produtores (e.g., [{'name': 'Nome', 'property': 'Propriedade'}])."}), 400

    conn = None
    added_count = 0
    updated_count = 0
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for item in producers_to_import:
            if isinstance(item, dict) and 'name' in item:
                name = item['name'].strip()
                property_name = item.get('property', '').strip() # Pega a propriedade, padrão vazio

                # Normaliza os valores para inserção e comparação
                normalized_name = name
                normalized_property_name = property_name if property_name is not None else ""

                if normalized_name:
                    # Tenta inserir o produtor. A cláusula ON CONFLICT usará o índice funcional.
                    cur.execute(
                        "INSERT INTO producers (name, property_name) VALUES (%s, %s) "
                        "ON CONFLICT (TRIM(LOWER(name)), TRIM(LOWER(property_name))) DO NOTHING;",
                        (normalized_name, normalized_property_name)
                    )
                    if cur.rowcount > 0: # Se uma linha foi inserida
                        added_count += 1
                    else:
                        updated_count += 1 # Se não foi inserida, significa que já existia
        conn.commit()
        cur.close()
        return jsonify({"message": f"Importação concluída. {added_count} novos produtores adicionados, {updated_count} produtores existentes (não atualizados)."}), 200
    except Exception as e:
        print(f"Erro ao importar nomes de produtores: {e}")
        traceback.print_exc()
        return jsonify({"message": "Erro interno do servidor ao importar nomes de produtores."}), 500
    finally:
        if conn:
            conn.close()

# NOVO ENDPOINT: Para obter nomes de caminhoneiros
@app.route('/api/drivers', methods=['GET'])
def get_driver_names():
    """Retorna uma lista de nomes de caminhoneiros únicos do banco de dados."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM drivers ORDER BY name")
        drivers = [{"id": str(row[0]), "name": row[1]} for row in cur.fetchall()]
        cur.close()
        return jsonify(drivers)
    except Exception as e:
        print(f"Erro ao buscar nomes de caminhoneiros: {e}")
        traceback.print_exc()
        return jsonify({"message": "Erro interno do servidor ao buscar nomes de caminhoneiros."}), 500
    finally:
        if conn:
            conn.close()

# NOVO ENDPOINT: Para adicionar um único caminhoneiro
@app.route('/api/drivers', methods=['POST'])
def add_single_driver():
    """Adiciona um único caminhoneiro ao banco de dados."""
    data = request.get_json()
    driver_name = data.get('name')

    print(f"Recebido POST para /api/drivers: Nome='{driver_name}'")

    if not driver_name or driver_name.strip() == '':
        return jsonify({"message": "O nome do caminhoneiro não pode ser vazio."}), 400

    normalized_driver_name = driver_name.strip()

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT id FROM drivers WHERE TRIM(LOWER(name)) = TRIM(LOWER(%s));", (normalized_driver_name,))
        existing_driver = cur.fetchone()
        if existing_driver:
            cur.close()
            return jsonify({"message": "Caminhoneiro com o mesmo nome já existe."}), 409

        cur.execute("INSERT INTO drivers (name) VALUES (%s) RETURNING id;", (normalized_driver_name,))
        driver_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        return jsonify({"id": str(driver_id), "name": normalized_driver_name}), 201
    except Exception as e:
        print(f"Erro ao adicionar caminhoneiro: {e}")
        traceback.print_exc()
        return jsonify({"message": "Erro interno do servidor ao adicionar caminhoneiro."}), 500
    finally:
        if conn:
            conn.close()

# NOVO ENDPOINT: Para deletar um caminhoneiro
@app.route('/api/drivers', methods=['DELETE'])
def delete_driver_route(): # Renomeado para evitar conflito com a função add_driver_if_not_exists
    """Deleta um caminhoneiro do banco de dados pelo nome."""
    data = request.get_json()
    driver_name = data.get('name')

    print(f"Recebido DELETE para /api/drivers: Nome='{driver_name}'")

    if not driver_name or driver_name.strip() == '':
        return jsonify({"message": "O nome do caminhoneiro é obrigatório para a exclusão."}), 400

    normalized_driver_name = driver_name.strip()

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("DELETE FROM drivers WHERE TRIM(LOWER(name)) = TRIM(LOWER(%s));", (normalized_driver_name,))
        conn.commit()
        
        if cur.rowcount > 0:
            cur.close()
            return jsonify({"message": "Caminhoneiro removido com sucesso."}), 204
        else:
            cur.close()
            return jsonify({"message": "Caminhoneiro não encontrado ou já removido."}), 404
    except Exception as e:
        print(f"Erro ao deletar caminhoneiro: {e}")
        traceback.print_exc()
        return jsonify({"message": "Erro interno do servidor ao deletar caminhoneiro."}), 500
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    app.run(debug=True, port=5000) # Executa o Flask na porta 5000
