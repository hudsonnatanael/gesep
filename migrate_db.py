#!/usr/bin/env python3
"""Migrate database to add default temperature values"""
import requests
import sys

API_URL = "http://192.168.0.7:8000/api/debug/migrate-temperatura"

print("🔄 Migrando banco de dados...")
print(f"URL: {API_URL}\n")

try:
    response = requests.get(API_URL, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        print("✅ Migração concluída!")
        print(f"   Registros atualizados: {data.get('records_updated', 0)}")
        print(f"   Ação: {data.get('action', '')}")
    else:
        print(f"❌ Erro: Status {response.status_code}")
        print(f"   Resposta: {response.text}")
        sys.exit(1)
        
except requests.exceptions.ConnectionError:
    print("❌ Erro: Não conseguiu conectar ao servidor")
    print(f"   Verifique se a API está rodando em {API_URL}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Erro: {e}")
    sys.exit(1)
