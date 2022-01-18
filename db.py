import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base

DB_USER = ...
DB_USER_PASSWORD = ...
DB_HOST = ...
DB_NAME = ...

Base = declarative_base()


class Pairs(Base):
    __tablename__ = 'pairs'
    user_id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    pair_id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    pair_name = sqlalchemy.Column(sqlalchemy.String)
    pair_url = sqlalchemy.Column(sqlalchemy.String)
    photo_id = sqlalchemy.Column(sqlalchemy.String)
    favorite = sqlalchemy.Column(sqlalchemy.BOOLEAN, server_default='FALSE')
    blacklist = sqlalchemy.Column(sqlalchemy.BOOLEAN, server_default='FALSE')


def create_session():
    engine = sqlalchemy.create_engine(
        f"postgresql://{DB_USER}:{DB_USER_PASSWORD}@{DB_HOST}/{DB_NAME}")
    Base.metadata.create_all(engine)
    # noinspection PyUnresolvedReferences
    Session = sqlalchemy.orm.sessionmaker(bind=engine)
    return Session()


def insert_to_db(session, user_id, pair_id, photo_id, pair_name, pair_url):
    row = Pairs(user_id=user_id, pair_id=pair_id, photo_id=photo_id,
                pair_name=pair_name, pair_url=pair_url)
    session.add(row)
    session.commit()


def check_db_for_user(session, user_id):
    query = session.query(Pairs.user_id).filter_by(user_id=user_id).all()
    return len(query) > 0


def check_db(session, user_id, pair_id):
    query = (
        session.query(Pairs.pair_id)
            .filter_by(pair_id=pair_id)
            .filter_by(user_id=user_id)
            .all()
    )
    return len(query) > 0


def add_to(column, session, user_id, pair_id):
    if column == 'favorite':
        opposite = 'blacklist'
    else:
        opposite = 'favorite'
    (
        session.query(Pairs)
            .filter_by(user_id=user_id)
            .filter_by(pair_id=pair_id)
            .update({column: True, opposite: False}, synchronize_session=False)
    )
    session.commit()


def clear_user(session, user_id, totally=False):
    if totally:
        session.query(Pairs).filter_by(user_id=user_id).delete()
    else:
        (
            session.query(Pairs)
                .filter_by(user_id=user_id)
                .filter_by(favorite=False)
                .filter_by(blacklist=False)
                .delete()
        )
    session.commit()


def get_favorites(session, user_id):
    query = (
        session.query(Pairs.pair_name, Pairs.pair_url, Pairs.photo_id)
            .filter_by(user_id=user_id)
            .filter_by(favorite=True)
            .all()
    )
    return query
