import gspread
from oauth2client.service_account import ServiceAccountCredentials

def conectar_planilha():
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", escopo)
    cliente = gspread.authorize(creds)
    planilha = cliente.open("Gastos Pessoais").sheet1
    return planilha

from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters
from datetime import datetime
import re
import pandas as pd

TOKEN = "8356122820:AAEM-_wZNRjLOjgMpl1lrFGPxbMtwy38Z70"

planilha = conectar_planilha()


async def registrar_gasto(update, context):
    texto = update.message.text.strip()

    # Ex: "Mercado 120"
    match = re.match(r"(.+?)\s+([\d.,]+)", texto)

    if not match:
        await update.message.reply_text("❌ Formato inválido. Ex: Mercado 120")
        return

    descricao = match.group(1)
    valor = match.group(2).replace(",", ".")
    data = datetime.now().strftime("%d/%m/%Y")

    planilha.append_row([data, descricao, valor])

    await update.message.reply_text(f"✅ Gasto registrado: {descricao} - R$ {valor}")



async def resumo_mes(update, context):
    registros = planilha.get_all_records()
    df = pd.DataFrame(registros)

    if df.empty:
        await update.message.reply_text("Nenhum gasto registrado.")
        return

    df["Data"] = pd.to_datetime(df["Data"], dayfirst=True)
    mes_atual = datetime.now().month

    df_mes = df[df["Data"].dt.month == mes_atual]

    if df_mes.empty:
        await update.message.reply_text("Nenhum gasto neste mês.")
        return

    total = df_mes["Valor"].astype(float).sum()

    texto = "📅 Gastos do mês:\n\n"
    for _, row in df_mes.iterrows():
        texto += f"{row['Descrição']} - R$ {row['Valor']}\n"

    texto += f"\n💰 Total: R$ {total:.2f}"
    await update.message.reply_text(texto)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("mes", resumo_mes))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, registrar_gasto))

    print("Bot rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()
