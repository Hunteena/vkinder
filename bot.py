import json
from operator import itemgetter
from random import randrange
from datetime import datetime
from time import sleep

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

import db

GROUP_ID = ...
GROUP_TOKEN = ...

PHOTOS_TO_SHOW = 3
OPPOSITE_SEX = {1: 2, 2: 1, 0: 0}
AGE_DIFFERENCE = 5


def launch_bot(user_token):
    vk_group = vk_api.VkApi(token=GROUP_TOKEN)
    bot_long_poll = VkBotLongPoll(vk_group, group_id=GROUP_ID)
    db_session = db.create_session()
    User = create_user_class(vk_group, db_session, user_token)
    return bot_long_poll, User


def is_new_message(event):
    return event.type == VkBotEventType.MESSAGE_NEW


def create_user_class(vk_group, session, user_token):
    class User:
        group = vk_group
        db = session
        vk = vk_api.VkApi(token=user_token)

        def __init__(self, user_id):
            self.conversation_status = 0

            user_info = self.get_info(user_id)
            self.id = user_info.get('id')
            self.first_name = user_info.get('first_name')
            self.relation = user_info.get('relation')
            self.sex = user_info.get('sex')

            birth_date = user_info.get('bdate')
            if birth_date is None or len(birth_date) < 6:
                self.age = None
            else:
                birth_date = datetime.strptime(birth_date, "%d.%m.%Y")
                today = datetime.today()
                if birth_date.replace(year=today.year) < today:
                    self.age = today.year - birth_date.year
                else:
                    self.age = today.year - birth_date.year - 1

            country, city = user_info.get('country'), user_info.get('city')
            if country:
                self.country_id = country['id']
                self.country_title = country['title']
            else:
                self.country_id = None
                self.country_title = None
            if city:
                self.city_id = city['id']
                self.city_title = city['title']
            else:
                self.city_id = None
                self.city_title = None

            self.pairs_generator, self.current_pair = None, None

        def get_info(self, user_id):
            fields = 'bdate, sex, city, relation, country'
            values = {'user_ids': user_id, 'fields': fields}
            info = self.group.method('users.get', values)
            return info[0]

        def write_msg(self, message):
            values = {
                'user_id': self.id,
                'message': message,
                'random_id': randrange(10 ** 7)
            }
            self.group.method('messages.send', values=values)

        def send_photos(self, peer):
            values = {
                'owner_id': peer['id'],
                'album_id': 'profile',
                'extended': 1
            }
            response = self.vk.method('photos.get', values=values)
            photos = []
            for photo in response.get('items'):
                likes = photo['likes']['count']
                comments = photo['comments']['count']
                photos.append({
                    'popularity': likes + comments,
                    'photo_id': photo['id']
                })
            photos.sort(key=itemgetter('popularity'), reverse=True)

            peer_name = f"{peer['first_name']} {peer['last_name']} "
            peer_url = f"https://vk.com/id{peer['id']}"
            for i in range(min([PHOTOS_TO_SHOW, len(photos)])):
                attachment = f"photo{peer['id']}_{photos[i]['photo_id']}"
                values = {
                    'user_id': self.id,
                    'attachment': attachment,
                    'content_source': json.dumps({
                        "type": "url",
                        "url": f"https://vk.com/{attachment}"
                    }),
                    'random_id': randrange(10 ** 7)
                }
                self.group.method('messages.send', values=values)
            self.write_msg(f"{peer_name} {peer_url}")

            best_photo = f"photo{peer['id']}_{photos[0]['photo_id']}"
            db.insert_to_db(self.db, self.id, peer['id'], best_photo,
                            peer_name, peer_url)
            self.conversation_status = 100

        def search_pairs(self):
            if not self.check_params():
                return
            values = {
                'count': 50,
                'sex': OPPOSITE_SEX[self.sex],
                'country': self.country_id,
                'hometown': self.city_title,
                'age_from': max(0, self.age - AGE_DIFFERENCE),
                'age_to': self.age + AGE_DIFFERENCE,
                'fields': 'city, relation',
                'has_photo': 1
            }
            result = self.vk.method('users.search', values=values)
            candidates = result.get('items')
            pairs = []
            for candidate in candidates:
                if not candidate['can_access_closed']:
                    continue
                city = candidate.get('city')
                if city is None:
                    continue
                if city['title'] != self.city_title:
                    continue
                relation = candidate.get('relation')
                if relation and relation != self.relation:
                    continue
                pair_in_db = db.check_db(self.db, self.id, candidate['id'])
                if pair_in_db:
                    continue

                pairs.append(candidate)

            self.pairs_generator = self.generate_next(pairs)
            self.next_pair()

        def generate_next(self, pairs):
            self.write_msg(f"Могу вести для вас список фаворитов "
                           f"и чёрный список. \n"
                           f"Отправьте + после информации о человеке "
                           f"и я занесу его в фаворитов.\n"
                           f"Отправьте - (знак минус) "
                           f"и он больше не выпадет в поиске")
            sleep(1)
            for pair in pairs:
                self.send_photos(pair)
                self.current_pair = pair
                yield

        def next_pair(self):
            try:
                next(self.pairs_generator)
            except StopIteration:
                self.write_msg(f"К сожалению, больше кандидатов нет.")

        def answer(self, request):
            if request == '?':
                self.write_msg(
                    f'Отправьте "да" для поиска.\n'
                    f'Отправьте "пока" для сброса введённых данных '
                    f'и завершения разговора.\n'
                )
                return
            elif request.lower() == 'да':
                self.search_pairs()
                return
            elif request.lower() == 'пока':
                self.write_msg(f'Была рада помочь! До встречи!')
                return 'delete'
            # elif request.lower() == 'статус':
            #     self.write_msg(f"{self.conversation_status=}")
            #     return

            if self.conversation_status == 0:
                self.initial()
            elif self.conversation_status == 5:
                if request == '+':
                    self.show_favorites()
                elif request == '-':
                    db.clear_user(self.db, self.id, True)
                elif request == '0':
                    db.clear_user(self.db, self.id, False)
                self.write_msg(f'Отправьте "да", чтобы начать поиск')
                self.conversation_status = 3
            elif self.conversation_status == 10:
                self.city_title = request.title()
                self.search_pairs()
            elif self.conversation_status == 20:
                try:
                    sex = int(request)
                    if sex not in [0, 1, 2]:
                        raise ValueError
                    self.sex = sex
                    self.search_pairs()
                except ValueError:
                    self.write_msg(
                        f"Не поняла Вашего ответа. Попробуйте ещё раз.")
            elif self.conversation_status == 30:
                try:
                    self.age = int(request)
                    self.search_pairs()
                except ValueError:
                    self.write_msg(
                        f"Не поняла Вашего ответа. Попробуйте ещё раз.")
            elif self.conversation_status == 40:
                try:
                    relation = int(request)
                    if relation not in range(8):
                        raise ValueError
                    self.relation = relation
                    self.search_pairs()
                except ValueError:
                    self.write_msg(
                        f"Не поняла Вашего ответа. Попробуйте ещё раз.")
            elif self.conversation_status == 100:
                if request == '+':
                    db.add_to('favorite', self.db, self.id,
                              self.current_pair['id'])
                elif request == '-':
                    db.add_to('blacklist', self.db, self.id,
                              self.current_pair['id'])
                self.next_pair()
            return

        def check_params(self):
            # parameters = [self.city_title, self.sex, self.age, self.relation]
            if (self.city_title is None or self.sex is None
                    or self.age is None or self.relation is None):
                self.write_msg(f"К сожалению, данных из Вашего профиля "
                               f"недостаточно для начала поиска. "
                               f"Пожалуйста, ответьте на вопрос.")
            else:
                return True

            if self.city_title is None:
                self.conversation_status = 10
                self.write_msg(f"Ваш город?")
            elif self.sex is None:
                self.conversation_status = 20
                self.write_msg(f"Ваш пол?"
                               f"Возможные значения:\n"
                               f"1 — женский;\n"
                               f"2 — мужской;\n"
                               f"0 — не указан.\n")
            elif self.age is None:
                self.conversation_status = 30
                self.write_msg(f"Ваш возраст?")
            elif self.relation is None:
                self.conversation_status = 40
                self.write_msg(f"Ваше семейное положение? "
                               f"Возможные значения:\n"
                               f"1 — не женат/не замужем;\n"
                               f"2 — есть друг/есть подруга;\n"
                               f"3 — помолвлен/помолвлена;\n"
                               f"4 — женат/замужем;\n"
                               f"5 — всё сложно;\n"
                               f"6 — в активном поиске;\n"
                               f"7 — влюблён/влюблена;\n"
                               f"8 — в гражданском браке;\n"
                               f"0 — не указано.")
            return False

        def initial(self):
            if db.check_db_for_user(self.db, self.id):
                self.write_msg(f"Привет, {self.first_name}!\n"
                               f"Рада снова Вас видеть! \n"
                               f"Отправьте +, чтобы увидеть фаворитов.\n"
                               f"Если хотите начать поиск с чистого листа, "
                               f"но сохранить список фаворитов и чёрный "
                               f"список, отправьте 0 (ноль).\n"
                               f"Если хотите полностью очистить историю "
                               f"поиска, отправьте - (минус).\n"
                               f"(Для получения списка команд "
                               f"отправьте ? в любой момент)")
                self.conversation_status = 5

            else:
                self.write_msg(f"Привет, {self.first_name}!\n"
                               f"Меня зовут Вика, "
                               f"я чат-бот сервиса знакомств VKinder. "
                               f'Отправьте "да" для поиска.\n'
                               f'Отправьте "пока" для сброса введённых данных '
                               f'и завершения разговора.\n'
                               f"(Для получения этого списка команд "
                               f"отправьте ? в любой момент)")
                self.search_pairs()

        def show_favorites(self):
            favorites = db.get_favorites(self.db, self.id)
            for name, url, photo in favorites:
                values = {
                    'user_id': self.id,
                    'attachment': photo,
                    'message': f"{name} {url}",
                    'content_source': json.dumps({
                        "type": "url",
                        "url": f"https://vk.com/{photo}"
                    }),
                    'random_id': randrange(10 ** 7)
                }
                self.group.method('messages.send', values=values)

            self.conversation_status = 3

    return User
