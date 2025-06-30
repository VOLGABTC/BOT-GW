# --- VERSION FINALE V7 - COMPTE A REBOURS SECONDES ---
import os
import json
import random
import datetime
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import telegram.error

# --- Configuration ---
# !!! METTEZ VOTRE PROPRE ID TELEGRAM ICI !!!
ADMIN_USER_IDS = [6938893387] 

TOKEN = os.environ.get('TOKEN')
active_giveaways = {}

# --- Fichier de stockage pour les rôles ---
ROLES_FILE = "roles.json"

# --- Fonctions Utilitaires (inchangées) ---

def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def parse_duration(duration_str: str) -> datetime.timedelta | None:
    match = re.match(r"(\d+)([hmd])", duration_str.lower())
    if not match: return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm': return datetime.timedelta(minutes=value)
    elif unit == 'h': return datetime.timedelta(hours=value)
    elif unit == 'd': return datetime.timedelta(days=value)
    return None

def format_giveaway_message(chat_id: int) -> str:
    giveaway = active_giveaways.get(chat_id)
    if not giveaway: return "Aucun giveaway en cours."
    prize, end_time, host = giveaway['prize'], giveaway['end_time'], giveaway['host_mention']
    participants_count, winners_count = len(giveaway['participants']), giveaway['winners_count']
    now = datetime.datetime.now(end_time.tzinfo)
    time_left = end_time - now
    if time_left.total_seconds() <= 0:
        time_left_str = "terminé !"
    else:
        days, remainder = divmod(int(time_left.total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        if days > 0: time_left_str = f"dans {days}j {hours}h"
        elif hours > 0: time_left_str = f"dans {hours}h {minutes}m"
        elif minutes > 0: time_left_str = f"dans {minutes}m {seconds}s"
        else: time_left_str = f"dans {seconds}s"
    end_time_str = end_time.strftime("%d %b %Y à %H:%M")
    message = (
        f"🎉 *{prize}* 🎉\n\n"
        f"*Se termine :* {time_left_str} \\(le {end_time_str}\\)\n"
        f"*Organisé par :* {host}\n"
        f"*Participants :* {participants_count}\n"
        f"*Gagnants :* {winners_count}"
    )
    if giveaway.get("required_role"):
        message += f"\n*Réservé au rôle :* `{giveaway['required_role']}`"
    return message

# --- Fonctions de Gestion des Rôles (inchangées) ---

def load_roles():
    try:
        with open(ROLES_FILE, 'r') as f:
            content = f.read()
            if not content: return {}
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_roles(roles_data):
    with open(ROLES_FILE, 'w') as f:
        json.dump(roles_data, f, indent=4)

# --- Tâches planifiées (Jobs) ---

async def update_countdown_job(context: ContextTypes.DEFAULT_TYPE):
    """Tâche répétitive pour mettre à jour le message du compte à rebours."""
    chat_id = context.job.data['chat_id']
    if chat_id not in active_giveaways:
        context.job.schedule_removal()
        return
    giveaway = active_giveaways[chat_id]
    new_text = format_giveaway_message(chat_id)
    keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data='participate_giveaway')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=giveaway['message_id'], text=new_text,
            reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e): pass
        else:
            print(f"Erreur (BadRequest) lors de la mise à jour du compte à rebours : {e}")
            context.job.schedule_removal()
    except Exception as e:
        print(f"Erreur inattendue dans le job de compte à rebours: {e}")
        context.job.schedule_removal()

async def final_minute_trigger_job(context: ContextTypes.DEFAULT_TYPE):
    """Job qui se déclenche 60s avant la fin pour passer au décompte rapide."""
    chat_id = context.job.data['chat_id']
    print(f"Giveaway {chat_id}: Passage au décompte final (dernière minute).")
    # On arrête le job de mise à jour lente (toutes les 60s)
    slow_update_jobs = context.job_queue.get_jobs_by_name(f"gw_update_slow_{chat_id}")
    for job in slow_update_jobs:
        job.schedule_removal()
    # On démarre le job de mise à jour rapide (toutes les 3s)
    context.job_queue.run_repeating(update_countdown_job, interval=3, data={"chat_id": chat_id}, name=f"gw_update_fast_{chat_id}")

async def draw_winners_callback(context: ContextTypes.DEFAULT_TYPE):
    """Fonction appelée pour le tirage au sort final."""
    chat_id = context.job.data['chat_id']
    # On arrête tous les jobs de mise à jour restants (le rapide ou le lent)
    for job_name in [f"gw_update_slow_{chat_id}", f"gw_update_fast_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
    
    if chat_id not in active_giveaways: return
    giveaway = active_giveaways[chat_id]
    # ... (le reste de la logique de tirage est inchangée) ...
    participants = giveaway['participants']
    prize = giveaway['prize']
    final_message = f"🎉 Le giveaway pour *{prize}* est terminé \\! 🎉\n\n"
    required_role = giveaway.get("required_role")
    valid_participants = {}
    if required_role:
        roles = load_roles()
        if required_role in roles:
            for user_id, user_name in participants.items():
                if user_id in roles[required_role] or user_id in ADMIN_USER_IDS:
                    valid_participants[user_id] = user_name
    else: valid_participants = participants
    valid_participant_ids = list(valid_participants.keys())
    winners_count = min(giveaway['winners_count'], len(valid_participant_ids))
    if not valid_participant_ids:
        final_message += "Malheureusement, aucun participant valide n'a été trouvé pour ce giveaway\\. 😕"
    else:
        winner_ids = random.sample(valid_participant_ids, k=winners_count)
        winner_mentions = [f"🏆 [{escape_markdown_v2(valid_participants[wid])}](tg://user?id={wid})" for wid in winner_ids]
        final_message += "Félicitations aux gagnants :\n" + "\n".join(winner_mentions)
    await context.bot.send_message(chat_id, final_message, parse_mode=constants.ParseMode.MARKDOWN_V2)
    if chat_id in active_giveaways:
        del active_giveaways[chat_id]

# --- Commandes du Bot (la plupart sont inchangées) ---

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (inchangée) ...
    help_text = (
        "💡 *Voici la liste des commandes disponibles* 💡\n\n"
        "\\-\\-\\-\n\n"
        "*Commandes pour les Administrateurs*\n\n"
        "`/giveaway <gagnants> <durée> [@rôle] <prix>`\n"
        "_Lance un nouveau giveaway\\. Le rôle est optionnel\\._\n"
        "*Exemple:* `/giveaway 2 1h Super Lot`\n"
        "*Exemple avec rôle:* `/giveaway 1 30m @vip Lot VIP`\n\n"
        "`/annuler_giveaway`\n"
        "_Annule le concours en cours dans le chat\\._\n\n"
        "`/assigner_role <rôle>`\n"
        "_\\(En réponse à un message\\) Assigne un rôle à un utilisateur\\._\n\n"
        "`/retirer_role <rôle>`\n"
        "_\\(En réponse à un message\\) Retire un rôle à un utilisateur\\._\n\n"
        "`/help`\n"
        "_Affiche ce message d'aide\\._"
    )
    await update.message.reply_text(text=help_text, parse_mode=constants.ParseMode.MARKDOWN_V2)

async def assign_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (inchangée) ...
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
    # ... (inchangée) ...
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
        if not roles[role_name]: del roles[role_name]
        save_roles(roles)
        await update.message.reply_text(f"Le rôle '{role_name}' a été retiré à {target_user_name}.")
    else:
        await update.message.reply_text(f"{target_user_name} n'a pas (ou plus) le rôle '{role_name}'.")

async def cancel_giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annule un giveaway en cours et arrête tous les jobs associés."""
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("Désolé, seul un administrateur peut annuler un giveaway.")
        return
    chat_id = update.message.chat_id
    if chat_id not in active_giveaways:
        await update.message.reply_text("Il n'y a aucun giveaway en cours à annuler.")
        return
    # On arrête tous les jobs possibles
    for job_name in [f"gw_draw_{chat_id}", f"gw_update_slow_{chat_id}", f"gw_update_fast_{chat_id}", f"gw_final_minute_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
    
    giveaway = active_giveaways[chat_id]
    prize = giveaway['prize']
    cancelled_text = f"❌ *GIVEAWAY ANNULÉ* ❌\n\nLe concours pour *{prize}* a été annulé par un administrateur\\."
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=giveaway['message_id'], text=cancelled_text,
            parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=None
        )
    except Exception as e:
        print(f"Erreur en éditant le message d'annulation: {e}")
    if chat_id in active_giveaways:
        del active_giveaways[chat_id]
    await update.message.reply_text("Le giveaway a bien été annulé.")

async def giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lance un nouveau giveaway, avec toute la logique de jobs."""
    if update.effective_user.id not in ADMIN_USER_IDS:
        await update.message.reply_text("Désolé, seul un administrateur peut lancer un giveaway.")
        return
    chat_id = update.message.chat_id
    if chat_id in active_giveaways:
        await update.message.reply_text("Un giveaway est déjà en cours dans ce chat !")
        return
    args = context.args
    # ... (la logique de parsing des arguments est inchangée) ...
    if len(args) < 3:
        await update.message.reply_text("Format incorrect.\nUsage : `/giveaway <gagnants> <durée> [@rôle] <prix>`...")
        return
    try:
        winners_count = int(args[0])
        duration = parse_duration(args[1])
        required_role, prize_args, role_found = None, [], False
        for arg in args[2:]:
            if arg.startswith('@') and not role_found:
                potential_role = arg[1:].lower()
                roles = load_roles()
                if potential_role in roles:
                    required_role, role_found = potential_role, True
                else: prize_args.append(arg)
            else: prize_args.append(arg)
        prize = ' '.join(prize_args)
        if not prize or not duration or winners_count <= 0: raise ValueError("Arguments invalides")
    except (ValueError, IndexError):
        await update.message.reply_text("Format invalide...")
        return
        
    end_time = datetime.datetime.now(datetime.timezone.utc) + duration
    host_user = update.effective_user
    escaped_prize = escape_markdown_v2(prize)
    giveaway_data = {
        "prize": escaped_prize, "required_role": required_role, "end_time": end_time,
        "host_mention": host_user.mention_markdown_v2(), "winners_count": winners_count,
        "participants": {}, "message_id": None, "chat_id": chat_id
    }
    active_giveaways[chat_id] = giveaway_data
    
    message_text = format_giveaway_message(chat_id)
    keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data='participate_giveaway')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        sent_message = await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2)
        giveaway_data['message_id'] = sent_message.message_id
        
        # --- NOUVELLE LOGIQUE DE PLANIFICATION ---
        context.job_queue.run_once(draw_winners_callback, when=end_time, data={"chat_id": chat_id}, name=f"gw_draw_{chat_id}")
        
        # Si le giveaway dure plus de 65 secondes, on met en place le système à double vitesse
        if duration.total_seconds() > 65:
            # Job lent (toutes les 60s)
            context.job_queue.run_repeating(update_countdown_job, interval=60, first=60, data={"chat_id": chat_id}, name=f"gw_update_slow_{chat_id}")
            # Job de transition 60s avant la fin
            transition_time = end_time - datetime.timedelta(seconds=60)
            context.job_queue.run_once(final_minute_trigger_job, when=transition_time, data={"chat_id": chat_id}, name=f"gw_final_minute_{chat_id}")
        else:
            # Si le giveaway est court, on met directement le décompte rapide
            context.job_queue.run_repeating(update_countdown_job, interval=3, data={"chat_id": chat_id}, name=f"gw_update_fast_{chat_id}")

        await update.message.reply_text(f"Giveaway pour '{prize}' lancé ! Tirage dans {args[1]}.", reply_to_message_id=sent_message.message_id)
    except Exception as e:
        print(f"ERREUR CRITIQUE LORS DE L'ENVOI DU MESSAGE DE GIVEAWAY : {e}")
        await update.message.reply_text("Une erreur est survenue lors de la création de l'annonce.")
        if chat_id in active_giveaways: del active_giveaways[chat_id]

async def participate_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (inchangée) ...
    query = update.callback_query
    user, chat_id = query.from_user, query.message.chat_id
    if chat_id not in active_giveaways:
        await query.answer("Désolé, ce giveaway est déjà terminé.", show_alert=True)
        return
    giveaway = active_giveaways[chat_id]
    required_role = giveaway.get("required_role")
    if required_role and user.id not in ADMIN_USER_IDS:
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
            if "Message is not modified" in str(e): pass
            else: print(f"Ne peut pas éditer le message (pas de changement) : {e}")

def main():
    """Lance le bot."""
    if not TOKEN:
        print("Erreur: Le token n'a pas été trouvé.")
        return

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("start", help_command))
    application.add_handler(CommandHandler("giveaway", giveaway_command))
    application.add_handler(CommandHandler("annuler_giveaway", cancel_giveaway_command))
    application.add_handler(CommandHandler("assigner_role", assign_role_command))
    application.add_handler(CommandHandler("retirer_role", remove_role_command))
    application.add_handler(CallbackQueryHandler(participate_button, pattern='^participate_giveaway$'))
    
    print("Le bot de giveaway (version V7 - Décompte final) est démarré...")
    application.run_polling()

if __name__ == '__main__':
    main()