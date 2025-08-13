# p2p_trading_bot.py
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)
import os
import re
from dotenv import load_dotenv

load_dotenv()

# States
(
    NAME, EMAIL, CONTACT, LOCATION, BUY_SELL, CRYPTO,
    FIAT_CURRENCY, AMOUNT_RAW, USD_EQUIV, PAYMENT_METHOD,
    TIMELINE, KYC_DONE, NOTES
) = range(13)

# Env config
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
KYC_LINK = os.getenv("KYC_LINK", "https://example.com/secure-kyc")  # kept for manual use only

MIN_USD = 1000.0  # Minimum trade size as per PDF

def is_valid_email(email: str) -> bool:
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [['Start Trade Request']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "🚀 Welcome to BlockSecure P2P Trade Desk!\n\n"
        "We handle USDT, USDC, BTC, ETH vs INR / AED / EURO.\n"
        f"Minimum trade size: USD ${MIN_USD:.0f}. KYC required for first-time users.\n\n"
        "Press 'Start Trade Request' to begin or /cancel at any time.",
        reply_markup=reply_markup
    )
    return NAME

# 1. Name
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == 'Start Trade Request':
        await update.message.reply_text(
            "Section A — Basic Contact Info\n\n1) Full Name (must match KYC):",
            reply_markup=ReplyKeyboardRemove()
        )
        return NAME

    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("Please enter your full name (at least 3 characters).")
        return NAME
    context.user_data['name'] = name

    await update.message.reply_text("2) Email address (for transaction confirmation):")
    return EMAIL

# 2. Email
async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    if not is_valid_email(email):
        await update.message.reply_text("Please enter a valid email (e.g., name@example.com).")
        return EMAIL
    context.user_data['email'] = email

    await update.message.reply_text("3) Telegram / WhatsApp number (optional). Type 'skip' to omit:")
    return CONTACT

# 3. Contact
async def get_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == 'skip':
        context.user_data['contact'] = 'Not provided'
    else:
        context.user_data['contact'] = text

    await update.message.reply_text("4) Location / Country:")
    return LOCATION

# 4. Location
async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['location'] = update.message.text.strip()

    keyboard = [['Buy', 'Sell']]
    await update.message.reply_text(
        "Section B — Transaction Details\n\n5) Are you buying or selling crypto?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return BUY_SELL

# 5. Buy / Sell
async def get_buy_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['buy_sell'] = update.message.text.strip()

    # keep 'Other' only where it makes sense (crypto)
    keyboard = [['USDT', 'USDC', 'BTC'], ['ETH', 'Other']]
    await update.message.reply_text(
        "6) Which cryptocurrency? (choose or type 'Other')",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return CRYPTO

async def get_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data['crypto'] = text

    # removed 'Other' from fiat list as requested
    keyboard = [['INR', 'AED', 'EURO', 'USD']]
    await update.message.reply_text(
        "7) Which fiat currency will you trade against? (INR / AED / EURO / USD)",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return FIAT_CURRENCY

async def get_fiat_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['fiat_currency'] = update.message.text.strip()

    await update.message.reply_text(
        "8) Amount in crypto or fiat (please specify clearly, e.g. '1500 USD' or '0.05 BTC')"
    )
    return AMOUNT_RAW

# 8. Amount raw
async def get_amount_raw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['amount_raw'] = update.message.text.strip()

    await update.message.reply_text(
        "To enforce the minimum trade size (USD $1,000), please provide the USD equivalent of this trade.\n"
        "Enter USD equivalent as a number (e.g., '1500'):"
    )
    return USD_EQUIV

async def get_usd_equiv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        usd_val = float(re.sub(r'[^\d\.]', '', text))
    except:
        await update.message.reply_text("Please enter a numeric USD equivalent (e.g., 1500).")
        return USD_EQUIV

    context.user_data['usd_equiv'] = usd_val

    if usd_val < MIN_USD:
        # clearer buttons for proceed/cancel
        keyboard = [['Proceed', 'Cancel Request']]
        await update.message.reply_text(
            f"⚠️ The USD equivalent you entered (${usd_val:.2f}) is below the minimum trade size of ${MIN_USD:.0f}.\n"
            "You can either cancel or confirm that you want to proceed (subject to review).",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return PAYMENT_METHOD  # capture proceed/cancel here
    else:
        # normal flow to payment method (keep Other here since payment method can vary)
        keyboard = [
            ['Bank Transfer', 'UPI'],
            ['Cash in Person', 'Other']
        ]
        await update.message.reply_text(
            "9) Preferred payment method:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return PAYMENT_METHOD

# 9. Payment method (also used for below-min confirmation)
async def get_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # handle the below-minimum buttons 'Proceed' / 'Cancel Request'
    if text in ('Proceed', 'Cancel Request'):
        if text == 'Cancel Request':
            await update.message.reply_text(
                "Request cancelled due to below-minimum amount. You can start a new request with /start."
            )
            return ConversationHandler.END
        # user chose to proceed despite min -> ask for payment method now
        keyboard = [
            ['Bank Transfer', 'UPI'],
            ['Cash in Person', 'Other']
        ]
        await update.message.reply_text(
            "Understood — proceeding despite below-minimum amount. Please select preferred payment method:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return PAYMENT_METHOD

    # normal payment method selection
    context.user_data['payment_method'] = text

    # removed 'Other' from timeline options
    keyboard = [
        ['Immediate', 'Within 1 Hour'],
        ['Same Day']
    ]
    await update.message.reply_text(
        "10) Expected timeline for payment/settlement:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return TIMELINE

async def get_timeline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['timeline'] = update.message.text.strip()

    # KYC question - ask if ready to do KYC
    keyboard = [['Yes', 'No']]
    await update.message.reply_text(
        "Section C — Compliance\n\n11) Are you ready to do KYC with us? (Yes / No)",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return KYC_DONE

# 11. KYC
async def get_kyc_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text == 'yes':
        context.user_data['kyc_done'] = 'Yes - Ready for KYC'
        # proceed directly to notes (skip compliance agreement)
        await update.message.reply_text(
            "12) Any special instructions or notes for this trade? (optional)\nType 'skip' to omit.",
            reply_markup=ReplyKeyboardRemove()
        )
        return NOTES
    elif text == 'no':
        context.user_data['kyc_done'] = 'No - Not ready for KYC'
        # proceed directly to notes (skip compliance agreement)
        await update.message.reply_text(
            "12) Any special instructions or notes for this trade? (optional)\nType 'skip' to omit.",
            reply_markup=ReplyKeyboardRemove()
        )
        return NOTES
    else:
        # fallback - ask explicitly for Yes/No
        keyboard = [['Yes', 'No']]
        await update.message.reply_text(
            "Please reply 'Yes' or 'No' — Are you ready to do KYC with us?",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return KYC_DONE



async def get_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == 'skip':
        context.user_data['notes'] = ''
    else:
        context.user_data['notes'] = text

    # Submit request directly without confirmation
    ud = context.user_data
    message = (
        "🚨 NEW P2P TRADE REQUEST 🚨\n\n"
        "Section A — Contact Info\n"
        f"Name: {ud.get('name')}\nEmail: {ud.get('email')}\nContact: {ud.get('contact')}\nLocation: {ud.get('location')}\n\n"
        "Section B — Transaction Details\n"
        f"Buy/Sell: {ud.get('buy_sell')}\nCrypto: {ud.get('crypto')}\nAgainst: {ud.get('fiat_currency')}\n"
        f"Amount: {ud.get('amount_raw')}\nUSD Equivalent: ${ud.get('usd_equiv')}\nPayment Method: {ud.get('payment_method')}\n"
        f"Timeline: {ud.get('timeline')}\n\n"
        "Section C — Compliance\n"
        f"KYC Status: {ud.get('kyc_done')}\n\n"
        f"Notes: {ud.get('notes')}\n\n"
        f"⚠️ Minimum trade size: USD ${MIN_USD:.0f}"
    )
    if ADMIN_ID == 0:
        await update.message.reply_text("⚠️ ADMIN_ID not set — cannot forward request. Check .env.")
    else:
        await context.bot.send_message(chat_id=ADMIN_ID, text=message)

    await update.message.reply_text(
        "✅ Request submitted. Our trade desk will review and contact you shortly.\n"
        "Thank you!",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END



async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Request cancelled. Use /start to create a new trade request.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing in .env")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex('^Start Trade Request$'), start)
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_contact)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)],
            BUY_SELL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_buy_sell)],
            CRYPTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_crypto)],
            FIAT_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fiat_currency)],
            AMOUNT_RAW: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount_raw)],
            USD_EQUIV: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_usd_equiv)],
            PAYMENT_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_payment_method)],
            TIMELINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_timeline)],
            KYC_DONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_kyc_done)],
            NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_notes)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=600
    )

    app.add_handler(conv_handler)
    print("🚀 P2P Trading Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
