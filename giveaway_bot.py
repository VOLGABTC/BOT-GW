import json
import random
import datetime
import re # Pour analyser la durée
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Configuration ---
TOKEN = '7678099516:AAGR4fuHHQfg_VBPvrmSurStX-nY9IbfPIw'
ADMIN_USER_IDS = [6938893387, 6619876284]

# Nous allons stocker l'état du giveaway en mémoire vive pour cet exemple
# Clé: chat_id, Valeur: dictionnaire de données du giveaway
active_giveaways = {}

# --- Fonctions utilitaires ---

def parse_duration(duration_str: str) -> datetime.timedelta:
    """Analyse une chaîne de durée (ex: '10h', '30m', '2d') et retourne un timedelta."""
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

def format_giveaway_message(chat_id):
    """Met en forme le message du giveaway."""
    giveaway = active_giveaways.get(chat_id)
    if not giveaway:
        return "Aucun giveaway en cours."

    prize = giveaway['prize']
    end_time = giveaway['end_time']
    host = giveaway['host_mention']
    participants_count = len(giveaway['participants'])
    winners_count = giveaway['winners_count']
    
    # Calcul du temps restant
    now = datetime.datetime.now(end_time.tzinfo)
    time_left = end_time - now
    
    if time_left.total_seconds() <= 0:
        time_left_str = "terminé !"
    else:
        days, rem = divmod(time_left.seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        if days > 0:
            time_left_str = f"dans {days}j {hours}h"
        else:
            time_left_str = f"dans {hours}h {minutes}m"

    end_time_str = end_time.strftime("%d %B %Y %H:%M")

    return (
        f"🎉 **{prize}** 🎉\n\n"
        f"**Ends:** {time_left_str} ({end_time_str})\n"
        f"**Hosted by:** {host}\n"
        f"**Entries:** {participants_count}\n"
        f"**Winners:** {winners_count}\n"
    )

# --- Commandes du Bot ---

async def giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lance un nouveau giveaway (Admin seulement). Format: /giveaway <gagnants> <durée> <prix>"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("Désolé, seul un administrateur peut lancer un giveaway.")
        return

    chat_id = update.message.chat_id
    if chat_id in active_giveaways:
        await update.message.reply_text("Un giveaway est déjà en cours dans ce chat !")
        return

    try:
        _, winners_count_str, duration_str, *prize_list = context.args
        winners_count = int(winners_count_str)
        prize = ' '.join(prize_list)
        duration = parse_duration(duration_str)

        if not prize or not duration or winners_count <= 0:
            raise ValueError
    except (ValueError, IndexError):
        await update.message.reply_text("Format incorrect. Usage : `/giveaway <gagnants> <durée> <prix>`\nExemple: `/giveaway 2 1h Super Lot`")
        return

    end_time = datetime.datetime.now(datetime.timezone.utc) + duration
    host_user = update.effective_user
    
    active_giveaways[chat_id] = {
        "prize": prize,
        "end_time": end_time,
        "host_mention": host_user.mention_markdown(),
        "winners_count": winners_count,
        "participants": {}, # {user_id: user_full_name}
        "message_id": None,
        "chat_id": chat_id
    }

    message_text = format_giveaway_message(chat_id)
    keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data='participate_giveaway')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    sent_message = await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)
    
    # On stocke l'ID du message pour pouvoir le modifier plus tard
    active_giveaways[chat_id]['message_id'] = sent_message.message_id

    # On planifie le tirage au sort
    context.job_queue.run_once(draw_winners_callback, when=end_time, data={"chat_id": chat_id}, name=f"gw_{chat_id}")
    
    await update.message.reply_text(f"Giveaway lancé ! Le tirage aura lieu à {end_time.strftime('%H:%M:%S')}.")


async def participate_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le clic sur le bouton de participation."""
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    if chat_id not in active_giveaways:
        await query.answer("Ce giveaway est terminé.", show_alert=True)
        return

    giveaway = active_giveaways[chat_id]
    if user.id in giveaway['participants']:
        await query.answer("Vous participez déjà !", show_alert=True)
    else:
        giveaway['participants'][user.id] = user.full_name
        await query.answer("Participation enregistrée. Bonne chance !", show_alert=True)
        
        # Mettre à jour le message avec le nouveau nombre de participants
        new_text = format_giveaway_message(chat_id)
        keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data='participate_giveaway')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=giveaway['message_id'],
                text=new_text,
                reply_markup=reply_markup,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            print(f"Erreur lors de l'édition du message: {e}")


async def draw_winners_callback(context: ContextTypes.DEFAULT_TYPE):
    """Fonction appelée par le job_queue pour effectuer le tirage."""
    job_data = context.job.data
    chat_id = job_data['chat_id']
    
    if chat_id not in active_giveaways:
        return
        
    giveaway = active_giveaways[chat_id]
    participants_ids = list(giveaway['participants'].keys())
    winners_count = giveaway['winners_count']
    prize = giveaway['prize']

    final_message = f"🎉 Le giveaway pour **{prize}** est terminé ! 🎉\n\n"

    if not participants_ids:
        final_message += "Malheureusement, personne n'a participé. 😕"
    elif len(participants_ids) < winners_count:
        final_message += "Pas assez de participants pour tirer le nombre de gagnants prévus. Voici les heureux élus :\n"
        winners_count = len(participants_ids)

    if len(participants_ids) >= 1:
        winner_ids = random.sample(participants_ids, k=winners_count)
        winner_mentions = [f"[{giveaway['participants'][wid]}](tg://user?id={wid})" for wid in winner_ids]
        
        final_message += "Félicitations aux gagnants :\n" + "\n".join(f"🏆 {mention}" for mention in winner_mentions)
    
    # Envoie le message final dans le chat
    await context.bot.send_message(chat_id, final_message, parse_mode=constants.ParseMode.MARKDOWN)

    # Nettoie le giveaway terminé
    del active_giveaways[chat_id]


def main():
    """Lance le bot."""
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("giveaway", giveaway_command))
    application.add_handler(CallbackQueryHandler(participate_button, pattern='^participate_giveaway$'))

    print("Le bot de giveaway avancé est démarré...")
    application.run_polling()


if __name__ == '__main__':
    main()