#!/usr/bin/env python3
from flask import Flask,request,render_template,make_response,send_from_directory,session,redirect,logging,jsonify
import dataset,threading,datetime,random
from functools import wraps, update_wrapper
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.secret_key = "fdsafddsaksfds"
formatter = logging.logging.Formatter("[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s")
handler = RotatingFileHandler("log.txt", maxBytes=10000000, backupCount=5)
handler.setFormatter(formatter)
app.logger.addHandler(handler)
app.logger.setLevel(logging.logging.INFO)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = dataset.connect('sqlite:///data.db')
db_lock = threading.Lock()

ROLE_CLIENT                         = 1
ROLE_COPYRITER                  = 2
ROLE_COPYRITER_MANAGER= 3

ZAKAZ_STATE_PLACED          = 1
ZAKAZ_STATE_EXECUTING   = 2
ZAKAZ_STATE_FINISHED       = 3
ZAKAZ_STATE_CANCELED     = 4

ZAYAVKA_PLACED                 = 1
ZAYAVKA_REJECTED            = 2
ZAYAVKA_ACCEPTED            = 3
ZAYAVKA_EXECUTED           = 4

PRIZE_MONEY = 100
def intTryParse(value):
    try:
        return int(value), True
    except ValueError:
        return value, False


if not 't_users' in db.tables:
    db.query('''create table t_users (
                c_id INTEGER NOT NULL,
                c_fio TEXT,
                c_password TEXT,
                c_login TEXT,
                c_email TEXT,
                c_reg_date TEXT,
                c_id_role INTEGER NOT NULL,
                c_owned_money INTEGER NOT NULL,
                c_holded_money INTEGER NOT NULL,
                PRIMARY KEY (c_id))''')
    db.commit()
    app.logger.info("Created t_users table")
if not 't_zakaz' in db.tables:
    db.query('''create table t_zakaz (
                c_id INTEGER NOT NULL,
                c_uid INTEGER,
                c_money TEXT NOT NULL,
                c_create_date TEXT NOT NULL,
                c_duration TEXT NOT NULL,
                c_caption TEXT NOT NULL,
                c_id_state INTEGER NOT NULL,
                c_descr TEXT NOT NULL,
                PRIMARY KEY (c_id))''')
    db.commit()
    app.logger.info("Created t_zakaz table")
if not 't_zayavka' in db.tables:
    db.query('''create table t_zayavka (
                c_id INTEGER NOT NULL,
                c_id_copyriter INTEGER NOT NULL,
                c_id_zakaz INTEGER NOT NULL,
                c_id_state INTEGER NOT NULL,
                c_create_date TEXT NOT NULL,
                c_close_date TEXT NOT NULL,
                c_file_passed TEXT NOT NULL,
                c_comments TEXT NOT NULL,
                PRIMARY KEY (c_id))''')
    db.commit()
    app.logger.info("Created t_zayavka table")
db.executable.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('error', msg='login_required'))
        return f(*args, **kwargs)
    return decorated_function

def login_client(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not "user_type" in session:
            return render_template("error.html",error_message="Not logged in")
        if not session['user_type'] == ROLE_CLIENT:             
            return render_template("error.html",error_message="Not logged in as client")
        return f(*args, **kwargs)
    return decorated_function
def login_copyriter(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not "user_type" in session:
            return render_template("error.html",error_message="Not logged in")
        if not session['user_type'] == ROLE_CLIENT:             
            return render_template("error.html",error_message="Not logged in as copyriter")
        return f(*args, **kwargs)
    return decorated_function


@app.route("/")
def index():
    if not "user_login" in session:
        return render_template("index.html")
    print("Type",session['user_type'])
    if session['user_type'] == ROLE_CLIENT:
        return redirect("/client/list")
    if session['user_type'] == ROLE_COPYRITER:
        return redirect("/copyriter/list")

@login_copyriter
@app.route("/copyriter/list")
def copyriter_list():
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        u=db['t_users'].find_one(c_id=session['user_id'])
        db.executable.close()
        if not u:
            return redirect("/logout")
        return render_template("service-copyriter.html",fio=session['user_fio'],money=u['c_owned_money'])
    finally:
        db_lock.release()
@login_client
@app.route("/client/list")
def client_list():
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        z=db['t_users'].find_one(c_id=session['user_id'])
        if not z:
            return redirect("/logout")
        print(z)
        money = z['c_owned_money']
        h_money = z['c_holded_money']
        db.executable.close()
        if "message" in request.values:
            return render_template("service-client-apps.html",fio=session['user_fio'],message=request.values['message'],\
                    money=money,holded_money=h_money)
        else:
            return render_template("service-client-apps.html",fio=session['user_fio'],\
                    money=money,holded_money=h_money)
    finally:
        db_lock.release()
@login_client
@app.route("/client/cancel/<zid>")
def client_cancel(zid):
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        z=db['t_zakaz'].find_one(c_id=zid)
        if z:
            if z['c_uid'] == session['user_id']:
                db['t_zakaz'].update(dict(c_id=zid,c_id_state=ZAKAZ_STATE_CANCELED),['c_id'])
                db.executable.close()
                return jsonify({"status":"Success"})
            else:
                db.executable.close()
                return jsonify({"status":"Not owner"})
        db.executable.close()
        return jsonify({"status":"No such application"})
    finally:
        db_lock.release()
    
@login_client
@app.route("/client/create")
def client_create():
    if "message" in request.values:
        return render_template("service-client-create.html",fio=session['user_fio'],message=request.values['message'])
    else:
        return render_template("service-client-create.html",fio=session['user_fio'])

@login_client
@app.route('/client/createapp',methods=["POST"])
def ca():
    cap=request.values["caption_field"]
    dur=request.values["duration_field"]
    cost=request.values["cost_field"]
    descr=request.values["descr_field"]
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        dur_int,is_parsed_dur = intTryParse(dur)
        cost_int,is_parsed_cost = intTryParse(cost)
        if len(cap)<5 or len(descr)<10:
            return render_template("error.html",error_message="Invalid caption or description length")
        if is_parsed_dur == False or is_parsed_cost == False:
            return render_template("error.html",error_message="Not number on duration or cost")
        tm = datetime.datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
        #u=db['t_users'].find_one(c_id=session['user_id'])
        #if not u:
        #    return redirect("/logout")
        #if int(u['c_owned_money']) - int(u['c_holded_money']) < cost_int:
        #    return render_template("error.html",error_message="Not enough money holded")
        #new_holded_money = int(u['c_holded_money']) + cost_int
        #db['t_users'].update(dict(c_id=session['user_id'],c_holded_money=new_holded_money ),['c_id'])
        db['t_zakaz'].insert(dict(c_uid=session['user_id'],\
                                            c_money=str(cost_int),
                                            c_create_date=tm,
                                            c_duration=str(dur_int),
                                            c_caption=cap,
                                            c_id_state=ZAKAZ_STATE_PLACED,
                                            c_descr=descr))
        
        db.executable.close()
    finally:
        db_lock.release()
    return redirect("/client/list?message=Successfuly placed")

@login_copyriter
@app.route("/copyriter/trytake/<zid>")
def trytake(zid):
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        res = db['t_zayavka'].find_one(c_id_copyriter=session['user_id'],c_id_zakaz=zid)
        if res:
            return jsonify({"status":"Already taken"})
        tm = datetime.datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
        db['t_zayavka'].insert(dict(c_id_copyriter=session['user_id'],c_id_zakaz=zid,\
                        c_id_state=ZAYAVKA_PLACED,c_close_date='',c_create_date=tm,c_comments="",c_file_passed=""))
        db.executable.close()
        return jsonify({"status":"Success"})
    finally:
        db_lock.release()
@login_copyriter
@app.route("/copyriter/comment/<zid>",methods=['POST'])
def copyriter_make_comment(zid):
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        zayavka=db['t_zayavka'].find_one(c_id=zid,c_id_copyriter=session['user_id'])
        if not zayavka:
            return jsonify({"status":"No such zayavka"})
        if not "mes" in request.values:
            return jsonify({"status":"No message provided"})
        if len(request.values['mes']) <1:
            return jsonify({"status":"Too short"})
        new_text=""
        new_text+= session['user_fio']+" "
        new_text+= "["+ datetime.datetime.now().strftime("%d.%m.%Y,%H-%M-%S") +"]\n"
        new_text+= request.values['mes'] + "\n"
        db['t_zayavka'].update(dict(c_id=zayavka['c_id'],c_comments=zayavka['c_comments']+new_text),['c_id'])
        db.executable.close()
        return jsonify({"status":"Success"})
    finally:
        db_lock.release()
@login_copyriter
@app.route("/copyriter/comments/<zid>")
def copyriter_get_comments(zid):
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        zayavka=db['t_zayavka'].find_one(c_id=zid,c_id_copyriter=session['user_id'])
        if not zayavka:
            return jsonify({"status":"No such zayavka"})
        c_comments=zayavka['c_comments']
        db.executable.close()
        return jsonify({"status":"Success",'data':c_comments})
    finally:
        db_lock.release()

@login_client
@app.route("/client/comment/<zid>",methods=['POST'])
def client_make_comment(zid):
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        zayavka=db['t_zayavka'].find_one(c_id=zid)
        if not zayavka:
            return jsonify({"status":"No such zayavka"})
        zakaz = db['t_zakaz'].find_one(c_id=zayavka['c_id_zakaz'])
        if not zakaz:
            return jsonify({"status":"No such zakaz"})
        if zakaz['c_uid'] != session['user_id']:
            return jsonify({"status":"Not your zayavka"})
        if not "mes" in request.values:
            return jsonify({"status":"No message provided"})
        new_text=""
        new_text+= session['user_fio']+" "
        new_text+= "["+ datetime.datetime.now().strftime("%d.%m.%Y,%H-%M-%S") +"]\n"
        new_text+= request.values['mes'] + "\n"
        db['t_zayavka'].update(dict(c_id=zayavka['c_id'],c_comments=zayavka['c_comments']+new_text),['c_id'])
        db.executable.close()
        return jsonify({"status":"Success"})
    finally:
        db_lock.release()
@login_client
@app.route("/client/comments/<zid>")
def client_get_comments(zid):
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        zayavka=db['t_zayavka'].find_one(c_id=zid)
        if not zayavka:
            return jsonify({"status":"No such zayavka"})
        zakaz = db['t_zakaz'].find_one(c_id=zayavka['c_id_zakaz'])
        if not zakaz:
            return jsonify({"status":"No such zakaz"})
        if zakaz['c_uid'] != session['user_id']:
            return jsonify({"status":"Not your zayavka"})
        c_comments=zayavka['c_comments']
        db.executable.close()
        return jsonify({"status":"Success",'data':c_comments})
    finally:
        db_lock.release()


@login_client
@app.route("/client/confirm/<zid>")
def client_confirm(zid):
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        zayavka=db['t_zayavka'].find_one(c_id=zid)
        if not zayavka:
            return jsonify({"status":"No such zayavka"})
        zakaz = db['t_zakaz'].find_one(c_id=zayavka['c_id_zakaz'])
        if not zakaz:
            return jsonify({"status":"No such zakaz"})
        if zakaz['c_uid'] != session['user_id']:
            return jsonify({"status":"Not your zakaz"})
        sender = db['t_users'].find_one(c_id=zakaz['c_uid'])
        if int(sender['c_owned_money']) - int(sender['c_holded_money']) < int(zakaz['c_money']):
            return jsonify({"status":"Not enough unholded money"})
        new_hold_money = int(sender['c_holded_money']) + int(zakaz['c_money'])
        db['t_users'].update(dict(c_id=sender['c_id'],c_holded_money=new_hold_money),['c_id'])
        db['t_zakaz'].update(dict(c_id=zakaz['c_id'],c_id_state=ZAKAZ_STATE_EXECUTING),['c_id'])
        db['t_zayavka'].update(dict(c_id=zayavka['c_id'],c_id_state=ZAYAVKA_ACCEPTED),['c_id'])
        db.executable.close()
        return jsonify({"status":"Success"})
    finally:
        db_lock.release()
@login_client
@app.route("/client/view/<zakazid>")
def client_view(zakazid):
    ret_data={}
    m=''
    if "message" in request.values:
        m=request.values['message']
    uploaded_data=None
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        zakaz = db['t_zakaz'].find_one(c_id=zakazid)
        if not zakaz:
            return render_template("error.html",error_message="No such zakaz")
        print(zakaz)
        if zakaz['c_id_state'] != ZAKAZ_STATE_EXECUTING and zakaz['c_id_state'] != ZAKAZ_STATE_FINISHED:
            return render_template("error.html",error_message="Invalid state of application")
        zayavka = db['t_zayavka'].find_one(c_id_zakaz=zakazid)
        if not zayavka:
            return render_template("error.html",error_message="No such zayavka")
        cr_id = zayavka['c_id_copyriter']
        cw = db['t_users'].find_one(c_id=cr_id)
        
        ret_data={ 'money'    :zakaz['c_money'],\
                        'caption'   :zakaz['c_caption'],\
                        'duration' :zakaz['c_duration'],\
                        'date'        :zakaz['c_create_date'],\
                        'state'       :zakaz['c_id_state'],\
                        'zid'          :zakaz['c_id'],\
                        'copyriter_fio':cw['c_fio'],\
                        'descr'      :zakaz['c_descr'],\
                        'taken_at' :zayavka['c_create_date']}
        if zayavka['c_file_passed'] and len(zayavka['c_file_passed'])>1:
            uploaded_data=zayavka['c_file_passed']
        db.executable.close()
    finally:
        db_lock.release()
    random_number = random.randint(1, 1000)
    return render_template("service-client-view.html",fio=session['user_fio'],data=ret_data,message=m,uploaded_data=uploaded_data,random_number =random_number )
@login_client
@app.route("/client/listapp")
def client_listapp():
    ret_data={"status":"Success",'data':[]}
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        dat = db['t_zakaz'].find(c_uid=session['user_id'])
        for d in dat:
            taken_zayavka = db['t_zayavka'].find(c_id_zakaz=d['c_id'])
            print("taken_zayavka ",taken_zayavka)
            udat = []
            for z in taken_zayavka :
                u = db['t_users'].find_one(c_id=z['c_id_copyriter'])
                udat.append(dict(fio=u['c_fio'],uid=u['c_id']))
            print("udat ",udat)
            state = ""
            if d['c_id_state'] == ZAKAZ_STATE_PLACED:
               state="Placed" 
            elif d['c_id_state'] == ZAKAZ_STATE_EXECUTING:
               state="Executing" 
            elif d['c_id_state'] == ZAKAZ_STATE_FINISHED:
               state="Finished"  
            elif d['c_id_state'] == ZAKAZ_STATE_CANCELED:
               state="Canceled" 
            ret_data['data'].append({'money':d['c_money'],\
                                                'caption':d['c_caption'],\
                                                'duration':d['c_duration'],\
                                                'date':d['c_create_date'],\
                                                'zid':d['c_id'],\
                                                'state':state,\
                                                'descr':d['c_descr'],\
                                                'taken_users': udat})
        db.executable.close()
    finally:
        db_lock.release()
    return jsonify(ret_data)
@login_client
@app.route("/client/finish/<zid>/<is_confirm>/<is_stay>")
def client_confirm_app(zid,is_confirm,is_stay):
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        zayavka=db['t_zayavka'].find_one(c_id=zid)
        if not zayavka:
            return jsonify({"status":"No such zayavka"})
        zakaz = db['t_zakaz'].find_one(c_id=zayavka['c_id_zakaz'])
        if not zakaz:
            return jsonify({"status":"No such zakaz"})
        if zakaz['c_uid'] != session['user_id']:
            return jsonify({"status":"Not your zakaz"})
        sender = db['t_users'].find_one(c_id=zakaz['c_uid'])
        receiver = db['t_users'].find_one(c_id=zayavka['c_id_copyriter'])
        
        new_sender_hold = int(sender['c_holded_money']) - int(zakaz['c_money'])
        new_sender_money = int(sender['c_owned_money']) - int(zakaz['c_money'])
        new_receiver_money = int(receiver['c_owned_money']) + int(zakaz['c_money'])
        tm = datetime.datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
        if is_confirm == '1':
            db['t_zayavka'].update(dict(c_id=zayavka['c_id'],c_id_state=ZAYAVKA_EXECUTED,\
                                                    c_close_date=tm),['c_id'])
            db['t_zakaz'].update(dict(c_id=zakaz['c_id'],c_id_state=ZAKAZ_STATE_FINISHED),['c_id'])
            db['t_users'].update(dict(c_id=zakaz['c_uid'],c_owned_money=new_sender_money,\
                                                                                c_holded_money=new_sender_hold),['c_id'])
            db['t_users'].update(dict(c_id=zayavka['c_id_copyriter'],\
                                                                            c_owned_money=new_receiver_money),['c_id'])
        else:
            db['t_zayavka'].update(dict(c_id=zayavka['c_id'],c_id_state=ZAYAVKA_REJECTED,\
                                        c_close_date=tm),['c_id'])
            if is_stay == "1":
                db['t_zakaz'].update(dict(c_id=zakaz['c_id'],c_id_state=ZAKAZ_STATE_PLACED),['c_id'])
            else:
                db['t_zakaz'].update(dict(c_id=zakaz['c_id'],c_id_state=ZAKAZ_STATE_CANCELED),['c_id'])
        db.executable.close()
        return jsonify({"status":"Success"})
    finally:
        db_lock.release()
@login_copyriter
@app.route("/copyriter/listapp")
def copyriter_listapp():
    ret_data={"status":"Success",'data':[]}
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        zayawki = [z for z in db['t_zayavka'].find(c_id_copyriter=session['user_id'])]
        zakazi = db['t_zakaz'].find()
        for d in zakazi:
            is_taken = 0
            for z in zayawki:
                if d['c_id'] == z['c_id_zakaz']:
                    is_taken = 1
                    break        
            
            if d['c_id_state'] == ZAKAZ_STATE_PLACED or \
                (d['c_id_state'] == ZAKAZ_STATE_EXECUTING and is_taken):
                ret_data['data'].append({'money':d['c_money'],\
                                                    'caption':d['c_caption'],\
                                                    'duration':d['c_duration'],\
                                                    'date':d['c_create_date'],\
                                                    'state':d['c_id_state'],\
                                                    'zid':d['c_id'],\
                                                    'descr':d['c_descr'],\
                                                    'is_taken': is_taken})
        db.executable.close()
    finally:
        db_lock.release()
    return jsonify(ret_data)

@login_copyriter
@app.route("/copyriter/uploads/<zid>")
def copyriter_uploads(zid):
    filename=""
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        zayawka = db['t_zayavka'].find_one(\
            c_id_copyriter=session['user_id'],\
            c_id_zakaz=zid,\
            c_id_state=ZAYAVKA_ACCEPTED\
        )
        if not zayawka:
            return render_template("error.html",error_message="No such zayavka")
        filename = zayawka['c_file_passed']
        db.executable.close()
    finally:
        db_lock.release()
    if filename != "":
        return send_from_directory("uploads",filename)
    else:
        return render_template("error.html",error_message="No such file")
@login_copyriter
@app.route("/copyriter/passpage/<zid>")
def copyriter_passpage(zid):
    ret_data={}
    m=''
    if "message" in request.values:
        m=request.values['message']
    uploaded_data=None
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        zayawka = db['t_zayavka'].find_one(\
            c_id_copyriter=session['user_id'],
            c_id_zakaz=zid
        )
        zakaz = db['t_zakaz'].find_one(c_id=zid)
        if zayawka and zakaz:
            ret_data={ 'money'    :zakaz['c_money'],\
                            'caption'   :zakaz['c_caption'],\
                            'duration' :zakaz['c_duration'],\
                            'date'        :zakaz['c_create_date'],\
                            'state'       :zakaz['c_id_state'],\
                            'state_zayavka':zayawka['c_id_state'],\
                            'finat'       :zayawka['c_close_date'],\
                            'zid'          :zakaz['c_id'],\
                            'descr'      :zakaz['c_descr'],\
                            'taken_at' :zayawka['c_create_date']}
            if zayawka['c_file_passed'] and len(zayawka['c_file_passed'])>1:
                uploaded_data=zayawka['c_file_passed']
        db.executable.close()
        random_number = random.randint(1, 1000)
        return render_template("service-copyriter-pass.htm",data=ret_data,message=m,\
                    uploaded_data=uploaded_data,random_number =random_number)
    finally:
        db_lock.release()


@login_copyriter
@app.route("/copyriter/pass",methods=['POST'])
def copyriter_pass():
    if not 'appfile' in request.files:
        return render_template("error.html",error_message="No file uploading")
    f=request.files['appfile']
    ext=f.filename[f.filename.rindex(".")+1:].lower()
    print(f.filename,ext)
    if ext != "pdf":
        return render_template("error.html",error_message="No pdf extension")
    tm = datetime.datetime.now().strftime("%d.%m.%Y,%H-%M-%S")
    zayavka_id=request.values['zid']
    fname=zayavka_id+"_"+tm+".pdf"
    f.save("uploads/"+fname)
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        db['t_zayavka'].update(dict(c_id=zayavka_id,c_file_passed=fname),['c_id'])
        db.commit()
        db.executable.close()
    finally:
        db_lock.release()
    return redirect('/copyriter/passpage/'+zayavka_id+"?message="+"Successfuly uploaded")
        
@app.route("/register")
def register():
    login=request.values["login_field"]
    password=request.values["password_field"]
    fio=request.values["fio_field"]
    email=request.values["email_field"]
    role=request.values["role_field"]
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        # Is this email unique
        res = db['t_users'].find_one(c_email=email)
        if res:
            return render_template("error.html",error_message="Email already registered")
        res = db['t_users'].find_one(c_login=login)
        if res:
            return render_template("error.html",error_message="Login already registered")
        
        role_index=0
        base_money=0
        if role == "Client":
            role_index=ROLE_CLIENT
            base_money=PRIZE_MONEY
        if role == "Copyriter":
            role_index=ROLE_COPYRITER
        if role_index==0:
            return render_template("error.html",error_message="No such role")
        
        tm = datetime.datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
        db['t_users'].insert(dict(c_login=login,c_password=password,c_fio=fio,\
             c_email=email,c_id_role=role_index,c_reg_date=tm,c_owned_money=base_money,c_holded_money=0 ))
        db.commit()
        db.executable.close()
    finally:
        db_lock.release()
    return render_template("index.html",message="Successfuly registered")

@app.route("/login")
def login():
    login=request.values["login_field"]
    password=request.values["password_field"]
    db_lock.acquire()
    try:
        db = dataset.connect('sqlite:///data.db')
        res = db['t_users'].find_one(c_login=login, c_password=password)
        if not res:
            return render_template("error.html",error_message="No such login or password")
        db.executable.close()
        session['user_id']=res["c_id"]
        session['user_login']=res["c_login"]
        session['user_fio']=res["c_fio"]
        session['user_type']=res["c_id_role"]
        return redirect("/")
    finally:
        db_lock.release()

@app.route("/logout")
def logout():
        session.pop('user_id', None)
        session.pop('user_login', None)
        session.pop('user_fio', None)
        session.pop('user_type', None)
        return redirect("/")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=3125,threaded=True,debug=False)
