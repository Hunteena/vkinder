from bot import launch_bot, is_new_message

if __name__ == '__main__':
    print('Введите токен пользователя, необходимый для запросов к VK API:')
    user_token = input()
    bot_long_poll, User = launch_bot(user_token)
    print('Бот сообщества ожидает сообщений от пользователей...')
    dialogs = {}
    current_user = None
    for event in bot_long_poll.listen():
        if is_new_message(event):
            user_id = event.message.from_id
            if user_id in dialogs:
                current_user = dialogs[user_id]
            else:
                current_user = User(user_id)
                dialogs[user_id] = current_user
            request = event.message.text
            action = current_user.answer(request)
            if action == 'delete':
                dialogs.pop(user_id)
