# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import openai
import os
from datetime import datetime
import tempfile
import traceback

app = Flask(__name__)
CORS(app)  # Tüm domain'lerden erişime izin ver

# DeepSeek API ayarları
openai.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
openai.api_base = "https://api.deepseek.com"

# Ana sayfa
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Borsa Analiz AI API",
        "version": "2.0",
        "author": "BorsaAnaliz Raporlar",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "health": "GET /health - Sistem durumu",
            "analyze": "POST /analyze - Excel analizi"
        }
    })

# Sağlık kontrolü
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "ai_connected": bool(openai.api_key),
        "timestamp": datetime.now().isoformat()
    })

# Excel analiz endpoint'i
@app.route('/analyze', methods=['POST'])
def analyze_excel():
    start_time = datetime.now()
    
    try:
        # 1. Dosya kontrolü
        if 'excel_file' not in request.files:
            return jsonify({
                "success": False,
                "error": "Excel dosyası yüklenmedi",
                "tip": "Lütfen .xlsx veya .xlsm dosyası yükleyin"
            }), 400
        
        file = request.files['excel_file']
        question = request.form.get('question', '').strip()
        
        if not file.filename:
            return jsonify({
                "success": False,
                "error": "Dosya seçilmedi"
            }), 400
        
        if not question:
            return jsonify({
                "success": False,
                "error": "Sorunuzu yazın",
                "tip": "'Hangi hisseler WT POZİTİF?' gibi bir soru sorun"
            }), 400
        
        # 2. Dosya uzantısı kontrolü
        allowed_extensions = {'.xlsx', '.xls', '.xlsm'}
        file_ext = os.path.splitext(file.filename.lower())[1]
        
        if file_ext not in allowed_extensions:
            return jsonify({
                "success": False,
                "error": f"Geçersiz dosya uzantısı: {file_ext}",
                "allowed": list(allowed_extensions)
            }), 400
        
        # 3. Dosya boyutu kontrolü (max 10MB)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            return jsonify({
                "success": False,
                "error": f"Dosya çok büyük: {file_size/(1024*1024):.1f}MB",
                "max_size": "10MB"
            }), 400
        
        # 4. Geçici dosya oluştur
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        
        try:
            # 5. Excel'i oku
            excel_file = pd.ExcelFile(tmp_path)
            sheet_names = excel_file.sheet_names
            
            # "Sinyaller" sheet'ini ara
            target_sheet = None
            for sheet in sheet_names:
                if 'sinyal' in sheet.lower():
                    target_sheet = sheet
                    break
            
            # Bulamazsak ilk sheet'i kullan
            if not target_sheet:
                target_sheet = sheet_names[0]
            
            df = pd.read_excel(tmp_path, sheet_name=target_sheet)
            
            # 6. Veriyi analiz et ve özetle
            data_info = {
                "filename": file.filename,
                "sheet": target_sheet,
                "total_rows": len(df),
                "total_columns": len(df.columns),
                "columns": df.columns.tolist()[:15],  # İlk 15 sütun
                "first_rows": df.head(3).to_dict('records') if len(df) > 0 else []
            }
            
            # 7. AI için optimize edilmiş veri özeti
            data_summary = f"""
            EXCEL VERİ ÖZETİ:
            • Dosya: {data_info['filename']}
            • Sheet: {data_info['sheet']}
            • Toplam Satır: {data_info['total_rows']}
            • Toplam Sütun: {data_info['total_columns']}
            • Ana Sütunlar: {', '.join(data_info['columns'][:10])}
            
            İLK 3 SATIR ÖRNEĞİ:
            {str(data_info['first_rows'])}
            """
            
            # 8. DeepSeek API'ye sor
            print(f"📤 DeepSeek'e soru gönderiliyor: {question[:50]}...")
            
            response = openai.ChatCompletion.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system", 
                        "content": """Sen bir borsa analiz uzmanısın. Kullanıcı sana Excel'deki BIST hisse verilerini yüklüyor.
                        
                        VERİ YAPISI:
                        - Hisse adları, fiyatlar, teknik göstergeler var
                        - WT sinyali (POZİTİF/NEGATİF)
                        - Pivot noktaları
                        - Hacim verileri
                        - Teknik göstergeler (RSI, MACD vb.)
                        
                        YANIT FORMATI:
                        1. Önce kısa bir özet
                        2. Madde madde analiz
                        3. Önemli bulgular
                        4. Tavsiyeler (sadece veriye dayalı)
                        
                        SADECE Excel'deki verilere dayan. Tahmin yapma.
                        Net, anlaşılır ve profesyonel bir dil kullan."""
                    },
                    {
                        "role": "user", 
                        "content": f"""EXCEL VERİSİ: {data_summary}
                        
                        KULLANICI SORUSU: {question}
                        
                        Lütfen bu Excel verisine göre analiz yap. Eğer sorduğu bilgi veride yoksa, "Bu bilgi excel'de bulunmuyor" de ve veride olan ilgili bilgileri göster."""
                    }
                ],
                max_tokens=2000,
                temperature=0.3,
                stream=False
            )
            
            answer = response.choices[0].message.content
            
            # 9. Yanıtı formatla
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return jsonify({
                "success": True,
                "answer": answer,
                "metadata": {
                    "processing_time_seconds": round(processing_time, 2),
                    "tokens_used": response.usage.total_tokens if hasattr(response, 'usage') else None,
                    "model": "deepseek-chat",
                    "data_info": data_info
                },
                "timestamp": datetime.now().isoformat()
            })
            
        except pd.errors.EmptyDataError:
            return jsonify({
                "success": False,
                "error": "Excel dosyası boş",
                "tip": "Dosyada veri olup olmadığını kontrol edin"
            }), 400
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Excel okuma hatası: {str(e)}",
                "traceback": traceback.format_exc() if app.debug else None
            }), 500
            
        finally:
            # Geçici dosyayı temizle
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except:
                pass
                
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Sunucu hatası: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }), 500

# Basit bir test endpoint'i
@app.route('/test', methods=['GET'])
def test_endpoint():
    return jsonify({
        "message": "Backend API çalışıyor!",
        "next_step": "Excel yüklemek için POST /analyze endpoint'ini kullanın",
        "example_questions": [
            "Hangi hisseler WT POZİTİF sinyal veriyor?",
            "En yüksek hacim artışı hangi hisselerde?",
            "Fiyatı pivot üstünde olan kaç hisse var?",
            "GÜÇLÜ POZİTİF olarak işaretlenmiş hisseleri listele"
        ]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    print(f"🚀 Borsa Analiz API başlatılıyor...")
    print(f"📡 Port: {port}")
    print(f"🔧 Debug: {debug_mode}")
    print(f"🤖 DeepSeek API: {'Bağlantı var' if openai.api_key else 'API key bekleniyor'}")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
