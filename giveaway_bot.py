# --- VERSION FINALE V3 - GESTION DES RÔLES INTÉGRÉE ---
import os
import json
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

# --- Fichier de stockage pour les rôles ---
ROLES_FILE = "roles.json"

# --- Fonctions Utilitaires ---

def escape_markdown_v2(text: str) -> str:
    """Échappe les caractères spéciaux pour le format MarkdownV2 de Telegram."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def parse_duration(duration_str: str) -> datetime.timedelta | None:
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

def format_giveaway_message(chat_id: int) -> str:
    """Met en forme le message du giveaway pour l'affichage."""
    giveaway = active_giveaways.get(chat_id)
    if not giveaway: return "Aucun giveaway en cours."
    prize = giveaway['prize']
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
    
    # On construit le message de base
    message = (
        f"🎉 *{prize}* 🎉\n\n"
        f"*Se termine :* {time_left_str} \\(le {end_time_str}\\)\n"
        f"*Organisé par :* {host}\n"
        f"*Participants :* {participants_count}\n"
        f"*Gagnants :* {winners_count}"
    )
    # On ajoute la ligne pour le rôle requis s'il existe
    if giveaway.get("required_role"):
        message += f"\n*Réservé au rôle :* `{giveaway['required_role']}`"
        
    return message

# --- Fonctions de Gestion des Rôles ---

def load_roles():
    """Charge les données des rôles depuis le fichier JSON."""
    try:
        with open(ROLES_FILE, 'r') as f:
            content = f.read()
            if not content: return {}
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_roles(roles_data):
    """Sauvegarde les données des rôles dans le fichier JSON."""
    with open(ROLES_FILE, 'w') as f:
        json.dump(roles_data, f, indent=4)

# --- Commandes du Bot ---

async def assign_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Assigne un rôle à un utilisateur."""
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("Désolé, seul un administrateur peut assigner un rôle.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Usage : Répondez au message d'un utilisateur avec `/assigner_role <nom_du_role>`")
        return
    try:
        role_name = context.args[0].lower()
        target_user_id = update.message.reply_to_message.from_user.id
        target_user_name = update.message.reply_to_message.from_user.full_name
    except IndexError:
        await update.message.reply_text("Format incorrect. N'oubliez pas le nom du rôle : `/assigner_role <nom_du_role>`")
        return
    roles = load_roles()
    if role_name not in roles:
        roles[role_name] = []
    if target_user_id not in roles[role_name]:
        roles[role_name].append(target_user_id)
        save_roles(roles)
        await update.message.reply_text(f"Le rôle '{role_name}' a bien été assigné à {target_user_name}.")
    else:
        await update.message.reply_text(f"{target_user_name} a déjà le rôle '{role_name}'.")

async def remove_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retire un rôle à un utilisateur."""
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("Désolé, seul un administrateur peut retirer un rôle.")
        return
    if not update.message or not update.message.reply_to_message:
        await update.message.reply_text("Usage : Répondez au message d'un utilisateur avec `/retirer_role <nom_du_role>`")
        return
    try:
        role_name = context.args[0].lower()
        target_user_id = update.message.reply_to_message.from_user.id
        target_user_name = update.message.reply_to_message.from_user.full_name
    except IndexError:
        await update.message.reply_text("Format incorrect. Usage: `/retirer_role <nom_du_role>`")
        return
    roles = load_roles()
    if role_name in roles and target_user_id in roles[role_name]:
        roles[role_name].remove(target_user_id)
        if not roles[role_name]:
            del roles[role_name]
        save_roles(roles)
        await update.message.reply_text(f"Le rôle '{role_name}' a été retiré à {target_user_name}.")
    else:
        await update.message.reply_text(f"{target_user_name} n'a pas (ou plus) le rôle '{role_name}'.")

async def cancel_giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annule un giveaway en cours."""
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("Désolé, seul un administrateur peut annuler un giveaway.")
        return
    chat_id = update.message.chat_id
    if chat_id not in active_giveaways:
        await update.message.reply_text("Il n'y a aucun giveaway en cours à annuler.")
        return
    giveaway = active_giveaways[chat_id]
    current_jobs = context.job_queue.get_jobs_by_name(f"gw_{chat_id}")
    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()
        print(f"Job pour le giveaway du chat {chat_id} annulé.")
    prize = giveaway['prize']
    cancelled_text = f"❌ *GIVEAWAY ANNULÉ* ❌\n\nLe concours pour *{prize}* a été annulé par un administrateur."
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=giveaway['message_id'], text=cancelled_text,
            parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=None
        )
    except Exception as e:
        print(f"Erreur en éditant le message d'annulation: {e}")
    del active_giveaways[chat_id]
    await update.message.reply_text("Le giveaway a bien été annulé.")

async def giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lance un nouveau giveaway, avec un rôle optionnel."""
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("Désolé, seul un administrateur peut lancer un giveaway.")
        return
    chat_id = update.message.chat_id
    if chat_id in active_giveaways:
        await update.message.reply_text("Un giveaway est déjà en cours dans ce chat ! Attendez la fin du précédent.")
        return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "Format incorrect.\nUsage : `/giveaway <gagnants> <durée> [rôle_optionnel] <prix>`\nExemple : `/giveaway 2 1h Super Lot`\nExemple avec rôle : `/giveaway 1 30m vip Lot Exclusif`"
        )
        return

    try:
        winners_count = int(args[0])
        duration = parse_duration(args[1])
        
        roles = load_roles()
        potential_role = args[2].lower()
        
        # On regarde si le 3ème argument est un rôle qui existe VRAIMENT
        if len(args) >= 4 and potential_role in roles:
            required_role = potential_role
            prize = ' '.join(args[3:])
        else:
            required_role = None
            prize = ' '.join(args[2:])

        if not prize or not duration or winners_count <= 0:
            raise ValueError("Arguments invalides")
            
    except (ValueError, IndexError):
        await update.message.reply_text("Format invalide. Vérifiez les nombres et la durée (ex: 10m, 2h, 1d).")
        return

    end_time = datetime.datetime.now(datetime.timezone.utc) + duration
    host_user = update.effective_user
    escaped_prize = escape_markdown_v2(prize)

    giveaway_data = {
        "prize": escaped_prize,
        "required_role": required_role,
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
        sent_message = await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2)
        giveaway_data['message_id'] = sent_message.message_id
        await update.message.reply_text(f"Giveaway pour '{prize}' lancé ! Tirage dans {args[1]}.", reply_to_message_id=sent_message.message_id)
    except Exception as e:
        print(f"ERREUR CRITIQUE LORS DE L'ENVOI DU MESSAGE DE GIVEAWAY : {e}")
        await update.message.reply_text("Une erreur est survenue lors de la création de l'annonce du giveaway.")
        if chat_id in active_giveaways:
            del active_giveaways[chat_id]

async def participate_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le clic sur le bouton de participation et vérifie le rôle."""
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    if chat_id not in active_giveaways:
        await query.answer("Désolé, ce giveaway est déjà terminé.", show_alert=True)
        return

    giveaway = active_giveaways[chat_id]
    
    required_role = giveaway.get("required_role")
    if required_role:
        roles = load_roles()
        if required_role not in roles or user.id not in roles[required_role]:
            await query.answer(f"Désolé, ce giveaway est réservé aux membres ayant le rôle '{required_role}'.", show_alert=True)
            return
            
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
    """Fonction appelée par le job_queue pour effectuer le tirage."""
    chat_id = context.job.data['chat_id']
    if chat_id not in active_giveaways: return
    giveaway = active_giveaways[chat_id]
    participants = giveaway['participants']
    participants_ids = list(participants.keys())
    winners_count = min(giveaway['winners_count'], len(participants_ids))
    prize = giveaway['prize']
    
    final_message = f"🎉 Le giveaway pour *{prize}* est terminé \\! 🎉\n\n"
    
    # On ajoute une vérification pour les rôles au moment du tirage
    required_role = giveaway.get("required_role")
    valid_participants = {}
    if required_role:
        roles = load_roles()
        if required_role in roles:
            for user_id, user_name in participants.items():
                if user_id in roles[required_role]:
                    valid_participants[user_id] = user_name
    else:
        valid_participants = participants

    valid_participant_ids = list(valid_participants.keys())
    winners_count = min(winners_count, len(valid_participant_ids))

    if not valid_participant_ids:
        final_message += "Malheureusement, aucun participant valide n'a été trouvé pour ce giveaway\\. 😕"
    else:
        winner_ids = random.sample(valid_participant_ids, k=winners_count)
        winner_mentions = [f"🏆 [{escape_markdown_v2(valid_participants[wid])}](tg://user?id={wid})" for wid in winner_ids]
        final_message += "Félicitations aux gagnants :\n" + "\n".join(winner_mentions)
        
    await context.bot.send_message(chat_id, final_message, parse_mode=constants.ParseMode.MARKDOWN_V2)
    del active_giveaways[chat_id]

def main():
    """Lance le bot."""
    if not TOKEN:
        print("Erreur: Le token n'a pas été trouvé. Assurez-vous de l'avoir configuré dans les variables d'environnement.")
        return

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("giveaway", giveaway_command))
    application.add_handler(CommandHandler("annuler_giveaway", cancel_giveaway_command))
    application.add_handler(CommandHandler("assigner_role", assign_role_command))
    application.add_handler(CommandHandler("retirer_role", remove_role_command))
    application.add_handler(CallbackQueryHandler(participate_button, pattern='^participate_giveaway$'))

    print("Le bot de giveaway (version V3 - Rôles) est démarré...")
    application.run_polling()

if __name__ == '__main__':
    main()