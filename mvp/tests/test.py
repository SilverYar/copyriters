
from pytest import *
from requests_html import *

import random
import string
def rs(stringLength=10):
    """Generate a random string of fixed length """
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(stringLength))

def test_reg():
    session = HTMLSession()
    r_cl = session.get("http://localhost:3125")
    r_cr = session.get("http://localhost:3125")
    (login_cl,passwd_cl,fio_cl,email_cl) = [rs(10) for i in range(4)]
    (login_cr,passwd_cr,fio_cr,email_cr) = [rs(10) for i in range(4)]
    r_cl.get("http://localhost:3125/register",params=dict(login_field=login_cl,\
                            password_field=passwd_cl,fio_field=fio_cl,email_field=email_cl,\
                            role_field="Client"))
    r_cr.get("http://localhost:3125/register",params=dict(login_field=login_cr,\
                            password_field=passwd_cr,fio_field=fio_cr,email_field=email_cr,\
                            role_field="Copyriter"))
