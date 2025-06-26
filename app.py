import os
import re
from flask import Flask, request, render_template, jsonify
from PIL import Image
import pytesseract

# --- CONFIGURAÇÃO IMPORTANTE (ESPECIALMENTE PARA WINDOWS) ---
# Se você está no Windows, descomente a linha abaixo e coloque o caminho
# exato de onde você instalou o Tesseract no Passo 2.
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# --- INÍCIO DO CÓDIGO DO SITE ---
app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Garante que a pasta de uploads exista
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def parse_ocr_text(text):
    """
    Esta função usa Expressões Regulares (RegEx) para extrair os dados
    do texto bagunçado que o OCR retorna. Compatível com Uber e 99.
    """
    data = {'valor': None, 'distancia_total': 0.0, 'tempo_total': 0}

    # Tenta encontrar o VALOR da corrida (ex: R$ 10,77)
    # Pega o primeiro valor R$ que encontrar, que geralmente é o principal.
    valor_match = re.search(r'R\$\s*(\d+,\d{2})', text)
    if valor_match:
        data['valor'] = float(valor_match.group(1).replace(',', '.'))

    # --- LÓGICA DE EXTRAÇÃO DE TEMPO ATUALIZADA (IGNORA MAIÚSCULA/MINÚSCULA) ---
    # Encontra "min", "Min", "minuto", "minutos", etc.
    potential_time_matches = re.findall(r'([a-zA-Z0-9]+)\s*[Mm]in', text)
    for match in potential_time_matches:
        cleaned_match = match.upper().replace('A', '').replace('Q', '9').replace('S', '5').replace('B', '8').replace('O', '0').replace('I', '1')
        try:
            data['tempo_total'] += int(cleaned_match)
        except ValueError:
            print(f"Não foi possível converter o tempo: '{cleaned_match}'")
            pass
    
    # LÓGICA DE EXTRAÇÃO DE DISTÂNCIA (ACEITA PONTO E VÍRGULA)
    distancia_km_matches = re.findall(r'(\d+[,.]\d+)\s*km', text)
    for d in distancia_km_matches:
        distancia_corrigida = d.replace(',', '.')
        data['distancia_total'] += float(distancia_corrigida)

    distancia_m_matches = re.findall(r'(\d+)\s*m\b', text)
    for d in distancia_m_matches:
        data['distancia_total'] += float(d) / 1000

    data['distancia_total'] = round(data['distancia_total'], 2)
    
    if not data['valor'] or data['distancia_total'] == 0 or data['tempo_total'] == 0:
        return None

    return data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analisar', methods=['POST'])
def analisar_corrida():
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400

    if file:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        try:
            # Extrai o texto da imagem usando o Tesseract
            extracted_text = pytesseract.image_to_string(Image.open(filepath), lang='eng')

            # Não precisamos mais imprimir o texto, pode remover ou comentar as 3 linhas abaixo
            print("--- INÍCIO DO TEXTO EXTRAÍDO ---")
            print(extracted_text)
            print("--- FIM DO TEXTO EXTRAÍDO ---")
            
            parsed_data = parse_ocr_text(extracted_text)

            if parsed_data is None:
                return jsonify({'error': 'Não foi possível extrair todos os dados da imagem. Tente uma imagem mais nítida.'}), 400

            valor = parsed_data['valor']
            distancia = parsed_data['distancia_total']
            tempo = parsed_data['tempo_total']
            
            custo_km = 0.90
            meta_hora = 40.0
            minimo_km = 1.60

            if tempo == 0 or distancia == 0:
                return jsonify({'error': 'Tempo ou distância extraídos como zero, cálculo impossível.'}), 400

            ganho_por_km = valor / distancia
            ganho_por_hora = valor / (tempo / 60)
            custo_total = distancia * custo_km
            lucro_liquido = valor - custo_total

            veredicto = ''
            if lucro_liquido <= 0:
                veredicto = 'PÉSSIMA (PREJUÍZO) ❌'
            elif ganho_por_km < minimo_km:
                veredicto = 'RUIM (R$/KM BAIXO) 👎'
            elif ganho_por_km >= 2.2 and ganho_por_hora >= (meta_hora * 1.5):
                veredicto = 'EXCELENTE ⭐'
            elif ganho_por_hora >= meta_hora:
                veredicto = 'BOA ✅'
            else:
                veredicto = 'ANALISE COM CUIDADO 🤔'

            result = {
                'veredicto': veredicto,
                'ganho_por_km': f'R$ {ganho_por_km:.2f}',
                'ganho_por_hora': f'R$ {ganho_por_hora:.2f}',
                'lucro_liquido': f'R$ {lucro_liquido:.2f}',
                'dados_extraidos': parsed_data
            }
            return jsonify(result)

        except Exception as e:
            return jsonify({'error': f'Ocorreu um erro no processamento: {str(e)}'}), 500
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

if __name__ == '__main__':
    from waitress import serve
    print("Servidor de produção iniciado em http://0.0.0.0:5000")
    serve(app, host='0.0.0.0', port=5000)