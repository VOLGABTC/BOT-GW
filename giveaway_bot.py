# --- VERSION FINALE V2 - AVEC PROTECTION MARKDOWN ---
import os
import random
import datetime
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Configuration ---
# !!! METTEZ VOTRE PROPRE ID TELEGRAM ICI !!!
ADMIN_USER_IDS = [6938893387] 

TOKEN = os.environ.get('TOKEN')
active_giveaways = {}

# --- Fonctions Utilitaires ---

def escape_markdown_v2(text: str) -> str:
    """Échappe les caractères spéciaux pour le format MarkdownV2 de Telegram."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def parse_duration(duration_str: str) -> datetime.timedelta | None:
    """Analyse une chaîne de durée (ex: '10h', '30m', '2d') et retourne un timedelta."""
    # ... (Le reste de cette fonction ne change pas) ...
    match = re.match(r"(\d+)([hmd])", duration_str.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm':
        return datetime.timedelta(minutes=value)
    elif unit == 'h':
        return datetime.timedelta(hours=value)
    elif unit == 'd':
        return datetime.timedelta(days=value)
    return None

def format_giveaway_message(chat_id: int) -> str:
    """Met en forme le message du giveaway pour l'affichage."""
    # ... (Le reste de cette fonction ne change pas, mais elle bénéficiera du texte déjà échappé) ...
    giveaway = active_giveaways.get(chat_id)
    if not giveaway: return "Aucun giveaway en cours."
    prize = giveaway['prize'] # Le prix est déjà échappé
    end_time = giveaway['end_time']
    host = giveaway['host_mention']
    participants_count = len(giveaway['participants'])
    winners_count = giveaway['winners_count']
    now = datetime.datetime.now(end_time.tzinfo)
    time_left = end_time - now
    if time_left.total_seconds() <= 0: time_left_str = "terminé !"
    else:
        days, remainder = divmod(time_left.seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        if days > 0: time_left_str = f"dans {days}j {hours}h"
        elif hours > 0: time_left_str = f"dans {hours}h {minutes}m"
        else: time_left_str = f"dans {minutes}m"
    end_time_str = end_time.strftime("%d %b %Y à %H:%M")
    return (
        f"🎉 *{prize}* 🎉\n\n"
        f"*Se termine :* {time_left_str} (le {end_time_str})\n"
        f"*Organisé par :* {host}\n"
        f"*Participants :* {participants_count}\n"
        f"*Gagnants :* {winners_count}"
    )

# --- Commandes du Bot ---

async def giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lance un nouveau giveaway. Format: /giveaway <gagnants> <durée> <prix>"""
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("Désolé, seul un administrateur peut lancer un giveaway.")
        return

    chat_id = update.message.chat_id
    if chat_id in active_giveaways:
        await update.message.reply_text("Un giveaway est déjà en cours dans ce chat ! Attendez la fin du précédent.")
        return

    try:
        winners_count_str, duration_str, *prize_list = context.args
        winners_count = int(winners_count_str)
        prize = ' '.join(prize_list)
        duration = parse_duration(duration_str)
        if not prize or not duration or winners_count <= 0:
            raise ValueError("Arguments invalides")
    except (ValueError, IndexError):
        # ... (La gestion d'erreur ne change pas) ...
        await update.message.reply_text(
            "Format incorrect.\n"
            "Usage : `/giveaway <gagnants> <durée> <prix>`\n"
            "Exemple : `/giveaway 2 1h Super Lot`\n"
            "(Durées : `m` pour minutes, `h` pour heures, `d` pour jours)"
        )
        return

    end_time = datetime.datetime.now(datetime.timezone.utc) + duration
    host_user = update.effective_user
    
    # !!! CORRECTION IMPORTANTE : ON ÉCHAPPE LE TEXTE FOURNI PAR L'UTILISATEUR !!!
    escaped_prize = escape_markdown_v2(prize)

    giveaway_data = {
        "prize": escaped_prize, # On stocke le prix déjà "nettoyé"
        "end_time": end_time,
        "host_mention": host_user.mention_markdown_v2(),
        "winners_count": winners_count,
        "participants": {},
        "message_id": None,
        "chat_id": chat_id
    }
    active_giveaways[chat_id] = giveaway_data

    message_text = format_giveaway_message(chat_id)
    keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data='participate_giveaway')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        # On utilise maintenant MarkdownV2, qui est plus strict mais plus joli
        sent_message = await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2)
        giveaway_data['message_id'] = sent_message.message_id
        # Confirmation que tout s'est bien passé
        await update.message.reply_text(f"Giveaway pour '{prize}' lancé ! Le tirage aura lieu dans {duration_str}.", reply_to_message_id=sent_message.message_id)
    except Exception as e:
        # Si ça échoue encore, on le saura dans les logs
        print(f"ERREUR CRITIQUE LORS DE L'ENVOI DU MESSAGE DE GIVEAWAY : {e}")
        await update.message.reply_text("Une erreur est survenue lors de la création de l'annonce du giveaway. Veuillez vérifier les logs.")
        # On nettoie le giveaway raté
        if chat_id in active_giveaways:
            del active_giveaways[chat_id]

# ... Le reste du code (participate_button, draw_winners_callback, main) ne change pas de la version finale précédente ...
async def participate_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    if chat_id not in active_giveaways:
        await query.answer("Désolé, ce giveaway est déjà terminé.", show_alert=True)
        return
    giveaway = active_giveaways[chat_id]
    if user.id in giveaway['participants']:
        await query.answer("Vous participez déjà !", show_alert=True)
    else:
        giveaway['participants'][user.id] = user.full_name
        await query.answer("Participation enregistrée. Bonne chance !", show_alert=True)
        new_text = format_giveaway_message(chat_id)
        keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data='participate_giveaway')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(text=new_text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2)
        except Exception as e:
            print(f"Ne peut pas éditer le message (pas de changement) : {e}")

async def draw_winners_callback(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data['chat_id']
    if chat_id not in active_giveaways: return
    giveaway = active_giveaways[chat_id]
    participants = giveaway['participants']
    participants_ids = list(participants.keys())
    winners_count = min(giveaway['winners_count'], len(participants_ids))
    prize = giveaway['prize'] # Le prix est déjà échappé
    final_message = f"🎉 Le giveaway pour *{prize}* est terminé !\n\n"
    if not participants_ids:
        final_message += "Malheureusement, personne n'a participé 😕"
    else:
        winner_ids = random.sample(participants_ids, k=winners_count)
        # On doit échapper les noms des gagnants aussi
        winner_mentions = [f"🏆 [{escape_markdown_v2(participants[wid])}](tg://user?id={wid})" for wid in winner_ids]
        final_message += "Félicitations aux gagnants :\n" + "\n".join(winner_mentions)
    await context.bot.send_message(chat_id, final_message, parse_mode=constants.ParseMode.MARKDOWN_V2)
    del active_giveaways[chat_id]

def main():
    if not TOKEN:
        print("Erreur: Le token n'a pas été trouvé.")
        return
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("giveaway", giveaway_command))
    application.add_handler(CallbackQueryHandler(participate_button, pattern='^participate_giveaway$'))
    print("Le bot de giveaway (version V2 Robuste) est démarré...")
    application.run_polling()

if __name__ == '__main__':
    main()