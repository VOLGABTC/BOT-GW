# --- VERSION FINALE V8 - GESTION DES SUJETS (TOPICS) ---
import os
import json
import random
import datetime
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import telegram.error

# --- Configuration ---
ADMIN_USER_IDS = [6938893387] 
TOKEN = os.environ.get('TOKEN')
active_giveaways = {}
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

def format_giveaway_message(giveaway_key: str) -> str:
    giveaway = active_giveaways.get(giveaway_key)
    if not giveaway: return "Aucun giveaway en cours."
    prize, end_time, host = giveaway['prize'], giveaway['end_time'], giveaway['host_mention']
    participants_count, winners_count = len(giveaway['participants']), giveaway['winners_count']
    now = datetime.datetime.now(end_time.tzinfo)
    time_left = end_time - now
    if time_left.total_seconds() <= 0: time_left_str = "terminé !"
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
    except (FileNotFoundError, json.JSONDecodeError): return {}

def save_roles(roles_data):
    with open(ROLES_FILE, 'w') as f:
        json.dump(roles_data, f, indent=4)

# --- Tâches planifiées (Jobs) ---
async def update_countdown_job(context: ContextTypes.DEFAULT_TYPE):
    giveaway_key = context.job.data['giveaway_key']
    if giveaway_key not in active_giveaways:
        context.job.schedule_removal()
        return
    giveaway = active_giveaways[giveaway_key]
    new_text = format_giveaway_message(giveaway_key)
    keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data=f'participate_{giveaway_key}')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await context.bot.edit_message_text(
            chat_id=giveaway['chat_id'], message_id=giveaway['message_id'], text=new_text,
            reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            print(f"Erreur compte à rebours: {e}")
            context.job.schedule_removal()

async def final_minute_trigger_job(context: ContextTypes.DEFAULT_TYPE):
    giveaway_key = context.job.data['giveaway_key']
    print(f"Giveaway {giveaway_key}: Passage au décompte final.")
    slow_update_jobs = context.job_queue.get_jobs_by_name(f"gw_update_slow_{giveaway_key}")
    for job in slow_update_jobs: job.schedule_removal()
    context.job_queue.run_repeating(update_countdown_job, interval=3, data={"giveaway_key": giveaway_key}, name=f"gw_update_fast_{giveaway_key}")

async def draw_winners_callback(context: ContextTypes.DEFAULT_TYPE):
    giveaway_key = context.job.data['giveaway_key']
    for job_name in [f"gw_update_slow_{giveaway_key}", f"gw_update_fast_{giveaway_key}"]:
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
    if giveaway_key not in active_giveaways: return
    giveaway = active_giveaways[giveaway_key]
    # --- On récupère les infos pour poster au bon endroit ---
    chat_id = giveaway['chat_id']
    message_thread_id = giveaway['message_thread_id']
    # ... logique de tirage ...
    participants, prize = giveaway['participants'], giveaway['prize']
    final_message = f"🎉 Le giveaway pour *{prize}* est terminé \\! 🎉\n\n"
    required_role, valid_participants = giveaway.get("required_role"), {}
    if required_role:
        roles = load_roles()
        if required_role in roles:
            for uid, uname in participants.items():
                if uid in roles[required_role] or uid in ADMIN_USER_IDS: valid_participants[uid] = uname
    else: valid_participants = participants
    valid_ids = list(valid_participants.keys())
    winners_count = min(giveaway['winners_count'], len(valid_ids))
    if not valid_ids:
        final_message += "Malheureusement, aucun participant valide n'a été trouvé pour ce giveaway\\. 😕"
    else:
        winner_ids = random.sample(valid_ids, k=winners_count)
        mentions = [f"🏆 [{escape_markdown_v2(valid_participants[wid])}](tg://user?id={wid})" for wid in winner_ids]
        final_message += "Félicitations aux gagnants :\n" + "\n".join(mentions)
    # --- On envoie le message dans le bon sujet ---
    await context.bot.send_message(chat_id, final_message, parse_mode=constants.ParseMode.MARKDOWN_V2, message_thread_id=message_thread_id)
    if giveaway_key in active_giveaways: del active_giveaways[giveaway_key]

# --- Commandes du Bot ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (inchangée) ...
    help_text = "💡 *Voici la liste des commandes disponibles* 💡\n\n\\-\\-\\-\n\n*Commandes pour les Administrateurs*\n\n`/giveaway <gagnants> <durée> [@rôle] <prix>`\n_Lance un nouveau giveaway\\. Le rôle est optionnel\\._\n*Exemple:* `/giveaway 2 1h Super Lot`\n*Exemple avec rôle:* `/giveaway 1 30m @vip Lot VIP`\n\n`/annuler_giveaway`\n_Annule le concours en cours dans le chat\\._\n\n`/assigner_role <rôle>`\n_\\(En réponse à un message\\) Assigne un rôle à un utilisateur\\._\n\n`/retirer_role <rôle>`\n_\\(En réponse à un message\\) Retire un rôle à un utilisateur\\._\n\n`/help`\n_Affiche ce message d'aide\\._"
    await update.message.reply_text(text=help_text, parse_mode=constants.ParseMode.MARKDOWN_V2)

async def assign_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (inchangée) ...
    if update.effective_user.id not in ADMIN_USER_IDS: return await update.message.reply_text("Désolé, seul un administrateur peut assigner un rôle.")
    if not update.message.reply_to_message: return await update.message.reply_text("Usage : Répondez au message d'un utilisateur avec `/assigner_role <nom_du_role>`")
    try:
        role_name, target_user_id, target_user_name = context.args[0].lower(), update.message.reply_to_message.from_user.id, update.message.reply_to_message.from_user.full_name
    except IndexError: return await update.message.reply_text("Format incorrect. N'oubliez pas le nom du rôle : `/assigner_role <nom_du_role>`")
    roles = load_roles()
    if role_name not in roles: roles[role_name] = []
    if target_user_id not in roles[role_name]:
        roles[role_name].append(target_user_id)
        save_roles(roles)
        await update.message.reply_text(f"Le rôle '{role_name}' a bien été assigné à {target_user_name}.")
    else: await update.message.reply_text(f"{target_user_name} a déjà le rôle '{role_name}'.")

async def remove_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (inchangée) ...
    if update.effective_user.id not in ADMIN_USER_IDS: return await update.message.reply_text("Désolé, seul un administrateur peut retirer un rôle.")
    if not update.message or not update.message.reply_to_message: return await update.message.reply_text("Usage : Répondez au message d'un utilisateur avec `/retirer_role <nom_du_role>`")
    try:
        role_name, target_user_id, target_user_name = context.args[0].lower(), update.message.reply_to_message.from_user.id, update.message.reply_to_message.from_user.full_name
    except IndexError: return await update.message.reply_text("Format incorrect. Usage: `/retirer_role <nom_du_role>`")
    roles = load_roles()
    if role_name in roles and target_user_id in roles[role_name]:
        roles[role_name].remove(target_user_id)
        if not roles[role_name]: del roles[role_name]
        save_roles(roles)
        await update.message.reply_text(f"Le rôle '{role_name}' a été retiré à {target_user_name}.")
    else: await update.message.reply_text(f"{target_user_name} n'a pas (ou plus) le rôle '{role_name}'.")

async def cancel_giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, message_thread_id = update.message.chat_id, update.message.message_thread_id
    giveaway_key = f"{chat_id}_{message_thread_id}" if message_thread_id else str(chat_id)
    if update.effective_user.id not in ADMIN_USER_IDS: return await update.message.reply_text("Désolé, seul un administrateur peut annuler un giveaway.")
    if giveaway_key not in active_giveaways: return await update.message.reply_text("Il n'y a aucun giveaway en cours à annuler dans ce sujet.")
    for job_name in [f"gw_draw_{giveaway_key}", f"gw_update_slow_{giveaway_key}", f"gw_update_fast_{giveaway_key}", f"gw_final_minute_{giveaway_key}"]:
        for job in context.job_queue.get_jobs_by_name(job_name): job.schedule_removal()
    giveaway = active_giveaways[giveaway_key]
    prize = giveaway['prize']
    cancelled_text = f"❌ *GIVEAWAY ANNULÉ* ❌\n\nLe concours pour *{prize}* a été annulé par un administrateur\\."
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=giveaway['message_id'], text=cancelled_text,
            parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=None
        )
    except Exception as e: print(f"Erreur en éditant le message d'annulation: {e}")
    if giveaway_key in active_giveaways: del active_giveaways[giveaway_key]
    await update.message.reply_text("Le giveaway a bien été annulé.")

async def giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_USER_IDS: return await update.message.reply_text("Désolé, seul un administrateur peut lancer un giveaway.")
    chat_id, message_thread_id = update.message.chat_id, update.message.message_thread_id
    giveaway_key = f"{chat_id}_{message_thread_id}" if message_thread_id else str(chat_id)
    if giveaway_key in active_giveaways: return await update.message.reply_text("Un giveaway est déjà en cours dans ce sujet !")
    args = context.args
    # ... (le reste de la fonction est lourdement modifié pour utiliser giveaway_key) ...
    if len(args) < 3: return await update.message.reply_text("Format incorrect...")
    try:
        winners_count, duration = int(args[0]), parse_duration(args[1])
        required_role, prize_args, role_found = None, [], False
        for arg in args[2:]:
            if arg.startswith('@') and not role_found:
                potential_role = arg[1:].lower()
                if potential_role in load_roles(): required_role, role_found = potential_role, True
                else: prize_args.append(arg)
            else: prize_args.append(arg)
        prize = ' '.join(prize_args)
        if not prize or not duration or winners_count <= 0: raise ValueError("Arguments invalides")
    except (ValueError, IndexError): return await update.message.reply_text("Format invalide...")
    end_time = datetime.datetime.now(datetime.timezone.utc) + duration
    giveaway_data = {
        "prize": escape_markdown_v2(prize), "required_role": required_role, "end_time": end_time,
        "host_mention": update.effective_user.mention_markdown_v2(), "winners_count": winners_count,
        "participants": {}, "message_id": None, "chat_id": chat_id, "message_thread_id": message_thread_id
    }
    active_giveaways[giveaway_key] = giveaway_data
    message_text = format_giveaway_message(giveaway_key)
    keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data=f'participate_{giveaway_key}')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        sent_message = await context.bot.send_message(chat_id, message_text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2, message_thread_id=message_thread_id)
        giveaway_data['message_id'] = sent_message.message_id
        job_data = {"giveaway_key": giveaway_key}
        context.job_queue.run_once(draw_winners_callback, when=end_time, data=job_data, name=f"gw_draw_{giveaway_key}")
        if duration.total_seconds() > 65:
            context.job_queue.run_repeating(update_countdown_job, interval=60, first=60, data=job_data, name=f"gw_update_slow_{giveaway_key}")
            transition_time = end_time - datetime.timedelta(seconds=60)
            context.job_queue.run_once(final_minute_trigger_job, when=transition_time, data=job_data, name=f"gw_final_minute_{giveaway_key}")
        else:
            context.job_queue.run_repeating(update_countdown_job, interval=3, data=job_data, name=f"gw_update_fast_{giveaway_key}")
        await update.message.reply_text(f"Giveaway pour '{prize}' lancé ! Tirage dans {args[1]}.", reply_to_message_id=sent_message.message_id)
    except Exception as e:
        print(f"ERREUR CRITIQUE LORS DE L'ENVOI DU MESSAGE DE GIVEAWAY : {e}")
        await update.message.reply_text("Une erreur est survenue lors de la création de l'annonce.")
        if giveaway_key in active_giveaways: del active_giveaways[giveaway_key]

async def participate_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # On récupère la clé unique depuis le bouton
    giveaway_key = query.data.replace('participate_', '')
    user = query.from_user
    if giveaway_key not in active_giveaways:
        await query.answer("Désolé, ce giveaway est déjà terminé.", show_alert=True)
        return
    giveaway = active_giveaways[giveaway_key]
    # Le reste de la logique est inchangé...
    required_role = giveaway.get("required_role")
    if required_role and user.id not in ADMIN_USER_IDS:
        roles = load_roles()
        if required_role not in roles or user.id not in roles[required_role]:
            await query.answer(f"Désolé, ce giveaway est réservé aux membres ayant le rôle '{required_role}'.", show_alert=True)
            return
    if user.id in giveaway['participants']: await query.answer("Vous participez déjà !", show_alert=True)
    else:
        giveaway['participants'][user.id] = user.full_name
        await query.answer("Participation enregistrée. Bonne chance !", show_alert=True)
        new_text = format_giveaway_message(giveaway_key)
        keyboard = [[InlineKeyboardButton("🎉 Participer", callback_data=query.data)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(text=new_text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN_V2)
        except Exception as e:
            if "Message is not modified" not in str(e): print(f"Ne peut pas éditer le message : {e}")

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
    # On utilise un regex pour capturer la clé unique du giveaway depuis le bouton
    application.add_handler(CallbackQueryHandler(participate_button, pattern=r'^participate_'))
    print("Le bot de giveaway (version V8 - Sujets) est démarré...")
    application.run_polling()

if __name__ == '__main__':
    main()