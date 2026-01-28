import re
import os
import tempfile
from datetime import datetime

import gspread
import pandas as pd
import openai

from oauth2client.service_account import ServiceAccountCredentials
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters
)

from dotenv import load_dotenv

# =========================
# CONFIGURAÇÕES
# =========================

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_KEY

PLANILHA_NOME = "Gastos Pessoais"

# =========================
# GOOGLE SHEETS
# =========================

def conectar_planilha():
    escopo = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        "credenciais.json", escopo
    )
    cliente = gspread.authorize(creds)
    return cliente.open(PLANILHA_NOME).sheet1

planilha = conectar_planilha()

# =========================
# REGRAS INTELIGENTES
# =========================

PALAVRAS_SAIDA = ["comprei", "paguei", "gastei", "pagar", "comprar"]
PALAVRAS_ENTRADA = ["recebi", "salario", "salário", "ganhei", "entrada"]

CATEGORIAS = {
    "alimentação": ["mercado", "almoço", "jantar", "lanche", "restaurante"],
    "transporte": ["uber", "ônibus", "onibus", "taxi", "combustivel"],
    "vestuário": ["camisa", "roupa", "calça", "sapato"],
    "renda": ["salario", "salário", "pagamento"],
    "extra": ["bla", "bla bla", "bla bla car", "venda", "vendi"],
}

def detectar_tipo(texto):
    texto = texto.lower()
    if texto.startswith("entrada"):
        return "Entrada"
    if texto.startswith("saida"):
        return "Saida"

    if any(p in texto for p in PALAVRAS_ENTRADA):
        return "Entrada"
    if any(p in texto for p in PALAVRAS_SAIDA):
        return "Saida"

    return "Saida"

def detectar_categoria(texto):
    texto = texto.lower()
    for categoria, palavras in CATEGORIAS.items():
        if any(p in texto for p in palavras):
            return categoria.capitalize()
    return "Outros"

# =========================
# REGISTRAR MOVIMENTAÇÃO
# =========================

async def registrar_movimentacao(update, context, texto):
    match = re.search(r"(.+?)\s+([\d.,]+)", texto)

    if not match:
        await update.message.reply_text(
            "❌ Não entendi.\nExemplo:\ncomprei mercado 120"
        )
        return

    descricao = match.group(1)
    valor = float(match.group(2).replace(",", "."))
    tipo = detectar_tipo(texto)
    categoria = detectar_categoria(texto)
    data = datetime.now().strftime("%d/%m/%Y")

    planilha.append_row([
        data,
        tipo,
        descricao.capitalize(),
        categoria,
        valor
    ])

    emoji = "💰" if tipo == "Entrada" else "💸"

    await update.message.reply_text(
        f"{emoji} {tipo} registrada!\n"
        f"{descricao.capitalize()} | {categoria}\n"
        f"R$ {valor:.2f}"
    )

# =========================
# TEXTO
# =========================

async def mensagem_texto(update, context):
    texto = update.message.text.strip()
    await registrar_movimentacao(update, context, texto)

# =========================
# VOZ
# =========================

async def mensagem_audio(update, context):
    audio = await update.message.voice.get_file()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
        caminho = f.name
        await audio.download_to_drive(caminho)

    with open(caminho, "rb") as audio_file:
        transcricao = openai.audio.transcriptions.create(
            file=audio_file,
            model="whisper-1"
        )

    os.remove(caminho)

    texto = transcricao.text
    await registrar_movimentacao(update, context, texto)

# =========================
# /MES
# =========================

async def resumo_mes(update, context):
    df = pd.DataFrame(planilha.get_all_records())

    if df.empty:
        await update.message.reply_text("Nenhuma movimentação registrada.")
        return

    df["Data"] = pd.to_datetime(df["Data"], dayfirst=True)
    mes = datetime.now().month

    df_mes = df[df["Data"].dt.month == mes]

    entradas = df_mes[df_mes["Tipo"] == "Entrada"]["Valor"].sum()
    saidas = df_mes[df_mes["Tipo"] == "Saida"]["Valor"].sum()
    saldo = entradas - saidas

    texto = "📅 Resumo do mês\n\n"
    for _, r in df_mes.iterrows():
        emoji = "💰" if r["Tipo"] == "Entrada" else "💸"
        texto += f"{emoji} {r['Descricao']} ({r['Categoria']}) - R$ {r['Valor']}\n"

    texto += (
        f"\n➕ Entradas: R$ {entradas:.2f}"
        f"\n➖ Saídas: R$ {saidas:.2f}"
        f"\n💼 Saldo: R$ {saldo:.2f}"
    )

    await update.message.reply_text(texto)

# =========================
# /SALDO
# =========================

async def saldo(update, context):
    df = pd.DataFrame(planilha.get_all_records())
    saldo = (
        df[df["Tipo"] == "Entrada"]["Valor"].sum()
        - df[df["Tipo"] == "Saida"]["Valor"].sum()
    )
    await update.message.reply_text(f"💼 Saldo total: R$ {saldo:.2f}")

# =========================
# /CATEGORIA
# =========================

async def categoria(update, context):
    if not context.args:
        await update.message.reply_text("Use: /categoria Alimentação")
        return

    categoria = context.args[0].capitalize()
    df = pd.DataFrame(planilha.get_all_records())
    df_cat = df[df["Categoria"] == categoria]

    if df_cat.empty:
        await update.message.reply_text("Nenhum registro nessa categoria.")
        return

    total = df_cat["Valor"].sum()
    texto = f"📊 {categoria}\n\n"

    for _, r in df_cat.iterrows():
        texto += f"{r['Descricao']} - R$ {r['Valor']}\n"

    texto += f"\n💰 Total: R$ {total:.2f}"
    await update.message.reply_text(texto)

# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("mes", resumo_mes))
    app.add_handler(CommandHandler("saldo", saldo))
    app.add_handler(CommandHandler("categoria", categoria))

    app.add_handler(MessageHandler(filters.VOICE, mensagem_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_texto))

    print("🤖 Bot financeiro rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()
