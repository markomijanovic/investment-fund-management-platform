# Detaljno objašnjenje IEP projekta

Ovaj dokument je napravljen da ga čitaš redom kao lekciju. Cilj nije da napamet naučiš kod, već da razumeš kako jedan zahtev prolazi kroz API, baze, Redis, blockchain, Kubernetes i periodični checker.

## Kako da koristiš ovaj dokument

Preporučen redosled učenja:

1. Pročitaj „Velika slika” i „Četiri vrste podataka”.
2. Nauči odobreni BUY tok, jer on povezuje skoro ceo projekat.
3. Prođi kroz auth, employee i director servis uz otvorene fajlove u editoru.
4. Prođi Solidity ugovor i checker zajedno — oni su dve polovine iste funkcionalnosti.
5. Nauči Dockerfile i `k8s/all.yaml` da umeš da objasniš pokretanje.
6. Pročitaj skripte da znaš šta se dešava kada kucaš `setup`, `start` i `test`.
7. Na kraju odgovori naglas na pitanja iz poslednjeg poglavlja.

Nemoj pokušavati da zapamtiš svaku liniju. Za odbranu treba da umeš da objasniš odgovornost fajla, tok podataka i razlog zbog kojeg je nešto urađeno.

---

# 1. Velika slika

Projekat predstavlja informacioni sistem investicionog fonda.

Postoje dve poslovne uloge:

- **employee** — registruje se, prijavljuje, pretražuje imovinu i predlaže kupovinu ili prodaju;
- **director** — vidi predloge, pokreće blockchain glasanje i čita zbirni finansijski izveštaj.

Sistem je podeljen na tri HTTP mikroservisa:

```text
Auth servis      localhost:5000
Employee servis  localhost:5001
Director servis  localhost:5002
```

Sva tri servisa unutar svojih kontejnera slušaju port `5000`. Kubernetes Service ih spolja izlaže na različitim portovima 5000, 5001 i 5002.

Pored HTTP servisa postoje:

- MySQL za korisnike;
- MongoDB za imovinu i istoriju obrađenih glasanja;
- Redis za privremene naloge i aktivna glasanja;
- Ganache kao lokalna Ethereum mreža;
- Solidity ugovor koji sprovodi glasanje;
- checker koji čita rezultat ugovora i ažurira baze.

Najvažniji tok izgleda ovako:

```text
employee
   │
   │ POST /create_buy_order
   ▼
Employee API ───────────────► Redis: pending order
                                  │
                                  │ GET /pending_orders
                                  ▼
                              director
                                  │
                                  │ POST /decision
                                  ▼
Director API ───────────────► deploy Solidity ugovora na Ganache
   │                              │
   └─────────────────────────────► Redis: active vote metadata
                                  │
                       glasači šalju transakcije
                                  │
                                  ▼
                             ugovor se završi
                                  │
                         CronJob pokrene checker
                                  │
                                  ▼
                         MongoDB dobija imovinu
                         Redis nalog se uklanja
```

Važno: endpoint `/decision` ne donosi odluku sam. On pokreće proces odlučivanja tako što deploy-uje ugovor i vraća transakcije koje glasači mogu poslati.

---

# 2. Zašto postoje četiri sistema za podatke

## 2.1 MySQL

MySQL čuva korisnike:

```text
users
├── id
├── forename
├── surname
├── email
├── password_hash
└── role
```

Zašto relacijska baza:

- struktura korisnika je stabilna;
- email mora biti jedinstven;
- registracija i brisanje koriste transakcije;
- SQL ograničenja dobro štite integritet podataka.

Lozinka se nikada ne čuva kao običan tekst. Čuva se samo hash napravljen Werkzeug funkcijom `generate_password_hash`.

## 2.2 MongoDB

MongoDB ima dve bitne kolekcije.

`assets` čuva imovinu:

```json
{
  "_id": "Mongo ObjectId",
  "name": "Zlatna poluga",
  "categories": ["metal", "zlato"],
  "buying_price": 10000,
  "buying_date": "datum",
  "info": {
    "purity": 24,
    "origin": {"country": "RS"}
  },
  "selling_price": 12000,
  "selling_date": "datum"
}
```

Polja za prodaju postoje samo ako je imovina prodata.

`processed_votes` čuva marker da je završeno glasanje već obrađeno:

```json
{
  "_id": "UUID naloga",
  "outcome": "APPROVED | REJECTED | VETOED",
  "processed_at": "datum",
  "applied": true,
  "contract_address": "0x..."
}
```

Zašto MongoDB:

- `info` može imati proizvoljna i ugnježdena polja;
- lako se pretražuju dinamički filteri poput `info.origin.country`;
- agregacioni pipeline odgovara direktorovom izveštaju.

## 2.3 Redis

Redis ne čuva trajnu imovinu. On čuva prolazno stanje procesa.

Za svaki nalog postoje dva zapisa:

```text
pending_orders                  Sorted Set UUID-eva
order:<uuid>                    JSON BUY ili SELL naloga
```

Kada direktor pokrene glasanje, dodaju se:

```text
active_votes                    Sorted Set UUID-eva
vote:<uuid>                     JSON metapodataka glasanja
```

Sorted Set koristi vreme kao score, pa UUID-evi ostaju uređeni prema vremenu nastanka. Konkretan JSON je u posebnom string ključu.

Zašto Redis:

- veoma brzo čita i piše privremene naloge;
- podržava atomske pipeline operacije;
- `SET NX EX` omogućava distribuirani lock;
- podaci više nisu potrebni kada checker primeni rezultat.

Redis u ovoj postavci nema PVC. Restart ili reset Redis-a može obrisati naloge, što je prihvatljivo za lokalni školski projekat, ali bi produkciona postavka zahtevala persistence ili drugi pouzdan queue.

## 2.4 Blockchain / Ganache

Blockchain čuva pravila i trenutno stanje glasanja:

- ko sme da glasa;
- ko je već glasao;
- broj glasova za i protiv;
- da li je glasanje završeno;
- da li je odobreno;
- da li je direktor uložio veto.

Ganache je lokalna razvojna Ethereum mreža sa unapred otključanim testnim nalozima. Ne koristi pravi novac niti javnu mrežu.

Blockchain ne menja MongoDB direktno. Ugovor samo čuva rezultat. Checker je most između blockchain rezultata i poslovne baze.

---

# 3. Kompletan tok odobrenog BUY naloga

Ovo je najvažniji scenario za odbranu.

## Korak 1: registracija i prijava

Zaposleni šalje:

```http
POST /register
Content-Type: application/json

{
  "forename": "Marko",
  "surname": "Mijanovic",
  "email": "marko@example.com",
  "password": "dovoljno-duga-lozinka"
}
```

Auth servis validira podatke, hash-uje lozinku i upisuje korisnika u MySQL sa ulogom `employee`.

Posle toga se korisnik prijavljuje:

```http
POST /login

{
  "email": "marko@example.com",
  "password": "dovoljno-duga-lozinka"
}
```

Auth vraća:

```json
{
  "accessToken": "JWT..."
}
```

JWT sadrži identitet korisnika i dodatne claim-ove: ime, prezime, email i ulogu.

## Korak 2: employee pravi BUY nalog

Zaposleni šalje token kroz header:

```http
Authorization: Bearer <JWT>
```

Zatim šalje:

```http
POST /create_buy_order

{
  "name": "Zlatna poluga",
  "categories": ["metal", "zlato"],
  "buying_price": 10000,
  "info": {
    "purity": 24,
    "origin": {"country": "RS"}
  }
}
```

Employee servis proverava:

- da sva četiri polja postoje;
- da categories nije prazna lista;
- da su sve kategorije neprazni stringovi do 256 znakova;
- da je cena pozitivan broj i nije boolean;
- da je name string odgovarajuće dužine;
- da je info objekat/dictionary.

Nalog se ne upisuje odmah u MongoDB, jer fond još nije kupio imovinu. Upisuje se u Redis kao predlog.

`add_order` generiše UUID, na primer:

```text
11111111-1111-4111-8111-111111111111
```

Zatim atomski upisuje:

```text
SET order:<uuid> <JSON naloga>
ZADD pending_orders <trenutno-vreme> <uuid>
```

## Korak 3: direktor pregleda naloge

Direktor se prijavljuje početnim nalogom:

```text
onlymoney@gmail.com
evenmoremoney
```

Njegov JWT sadrži ulogu `director`.

Poziv:

```http
GET /pending_orders
Authorization: Bearer <director JWT>
```

Director servis čita UUID-eve iz `pending_orders`, za svaki čita `order:<uuid>` i vraća JSON naloge.

## Korak 4: direktor pokreće glasanje

Direktor šalje UUID naloga i neparan broj jedinstvenih Ethereum adresa:

```http
POST /decision

{
  "uuid": "11111111-1111-4111-8111-111111111111",
  "voters": [
    "0x1111111111111111111111111111111111111111",
    "0x2222222222222222222222222222222222222222",
    "0x3333333333333333333333333333333333333333"
  ]
}
```

Director servis proverava:

- da UUID postoji i ima pravilan format;
- da nalog stvarno postoji u Redis-u;
- da voters postoji i nije prazna lista;
- da je svaka adresa oblika `0x` + 40 hex znakova;
- da nema duplih adresa, bez obzira na velika/mala slova;
- da je broj glasača neparan.

Zatim `BlockchainGateway.deploy` deploy-uje novi ugovor. U konstruktor se šalje lista glasača. Adresa koja deploy-uje ugovor postaje `director` unutar ugovora.

Metapodaci se čuvaju u Redis-u:

```json
{
  "uuid": "...",
  "contract_address": "0x...",
  "director_address": "0x90f8...",
  "voters": ["0x...", "0x...", "0x..."],
  "order": {"ceo originalni nalog": "..."}
}
```

Redis dobija:

```text
SET vote:<uuid> <JSON metapodataka>
ZADD active_votes <trenutno-vreme> <uuid>
```

API vraća tri nepotpisana transaction payload-a:

```json
{
  "approve_transaction": {
    "to": "adresa ugovora",
    "gas": 120000,
    "value": 0,
    "data": "enkodovan approve() poziv"
  },
  "reject_transaction": {
    "to": "adresa ugovora",
    "gas": 120000,
    "value": 0,
    "data": "enkodovan reject() poziv"
  },
  "veto_transaction": {
    "to": "adresa ugovora",
    "from": "adresa direktora",
    "gas": 120000,
    "value": 0,
    "data": "enkodovan veto() poziv"
  }
}
```

Server ne šalje approve/reject umesto glasača. Svaki glasač uzme payload i šalje ga sa svoje `from` adrese. Ugovor koristi `msg.sender` da proveri identitet glasača.

Ako se `/decision` ponovi za isti nalog, servis vidi postojeći `vote:<uuid>` i vraća transakcije za već postojeći ugovor. Ne deploy-uje drugi ugovor.

## Korak 5: glasači glasaju

Za tri glasača prag je:

```text
threshold = 3 / 2 + 1 = 2
```

Solidity koristi celobrojno deljenje, pa je `3 / 2` jednako `1`.

Prvi glasač pozove `approve()`:

```text
approveVotes = 1
ended = false
```

Drugi glasač pozove `approve()`:

```text
approveVotes = 2
ended = true
approved = true
```

Od tada `votingActive` odbija svaki novi approve, reject ili veto porukom `Voting ended.`.

## Korak 6: CronJob proverava rezultat

Kubernetes CronJob `contract-checker` se aktivira svakog minuta.

Njegov Pod:

1. čita UUID-eve iz `active_votes`;
2. čita `vote:<uuid>`;
3. uzima Redis lock za taj UUID;
4. čita `ended`, `approved` i `vetoed` sa ugovora;
5. ako `ended` nije true, ne radi ništa;
6. ako je odobren BUY, upisuje imovinu u MongoDB;
7. upisuje `processed_votes` marker;
8. uklanja `order:<uuid>`, UUID iz `pending_orders`, `vote:<uuid>` i UUID iz `active_votes`;
9. završava proces.

Pod dobija status `Completed`, što znači uspeh.

## Korak 7: imovina postaje vidljiva

Employee pozove `/search`. MongoDB sada sadrži novu imovinu sa datumom kupovine i `vote_uuid` poljem. Redis nalog više ne postoji.

---

# 4. Ostali ishodi glasanja

## 4.1 REJECT

Ako `rejectVotes` dostigne prag:

```text
ended = true
approved = false
vetoed = false
```

Checker upiše ishod `REJECTED` u `processed_votes`, ali ne dodaje i ne menja imovinu. Zatim briše privremeno Redis stanje.

## 4.2 VETO

Samo adresa koja je deploy-ovala ugovor može pozvati `veto()`.

Veto je moguć samo dok glasanje traje. Posle veta:

```text
ended = true
approved = false
vetoed = true
```

Checker evidentira `VETOED`, ali nalog nema efekat na MongoDB. Dalje glasanje nije moguće.

## 4.3 Odobren SELL

Employee prvo šalje MongoDB `_id` postojeće imovine i prodajnu cenu. Employee servis proverava da taj ObjectId postoji, pa pravi SELL nalog u Redis-u.

Ako glasanje bude odobreno, checker ne briše dokument imovine. On mu dodaje:

```text
selling_price
selling_date
sale_vote_uuid
```

Tako istorija kupovine ostaje sačuvana, a dokument dobija podatke o prodaji.

---

# 5. Direktorijum `common/`

Ovaj direktorijum sadrži kod koji koristi više servisa.

## `common/__init__.py`

Prazan fajl koji označava da je `common` Python paket. Zbog njega import izgleda kao:

```python
from common.config import sql_uri
```

## `common/config.py`

Centralizuje konfiguraciju iz environment promenljivih.

`env_int` čita tekstualnu environment promenljivu i pretvara je u integer.

`sql_uri` prvo proverava da li je postavljen kompletan `SQLALCHEMY_DATABASE_URI`. To je korisno u testovima, gde se prosleđuje `sqlite://`. Ako nije postavljen, sklapa MySQL URL iz:

```text
SQL_USER
SQL_PASSWORD
SQL_HOST
SQL_PORT
SQL_DATABASE
```

Unutar Kubernetes klastera `SQL_HOST=mysql` nije localhost. `mysql` je DNS ime Kubernetes Service-a.

`mongo_uri` i `mongo_database` daju adresu i ime MongoDB baze.

`redis_kwargs` vraća argumente za Redis klijent. `decode_responses=True` znači da Redis vraća Python stringove umesto bytes vrednosti.

## `common/clients.py`

Pravi stvarne klijente:

- `create_redis_client()` koristi `Redis(**redis_kwargs())`;
- `create_mongo_database()` povezuje se i odmah bira bazu `investment_fund`.

Servisi ove klijente kreiraju po defaultu, ali `create_app` dozvoljava ubacivanje fake klijenata u testovima. To je dependency injection.

## `common/security.py`

`configure_jwt(app)` registruje `JWTManager` i standardizuje odgovor kada token nedostaje.

`role_required(role)` je dekorator koji:

1. zahteva validan JWT preko `@jwt_required()`;
2. čita claim `role`;
3. poredi ga sa traženom ulogom;
4. tek onda poziva pravu endpoint funkciju.

Za pogrešnu ulogu vraća isti `401` format kao za nedostajući header, jer profesorov grader očekuje taj ugovor odgovora.

## `common/validation.py`

Sadrži male zajedničke validatore.

- `is_missing` smatra polje nedostajućim ako ga nema, ako je `None` ili prazan string.
- `missing_message` pravi tačan tekst `Field X is missing.`.
- `positive_number` prihvata pravi broj veći od nule, ali namerno odbija boolean. U Pythonu je `bool` podtip integera, pa je ta dodatna provera potrebna.
- `parse_iso8601` parsira datum i pretvara ga u UTC.
- `valid_ethereum_address` zahteva `0x` i tačno 40 heksadecimalnih znakova.

## `common/serialization.py`

MongoDB dokument ne treba direktno vratiti kroz Flask JSON jer:

- `_id` je `ObjectId`, a ne običan string;
- datetime treba vratiti u tačnom ISO-8601 obliku.

`serialize_asset` zato:

- `_id` pretvara u `id` string;
- datume pretvara u UTC format sa milisekundama i `Z` sufiksom;
- uključuje selling polja samo kada postoje.

## `common/orders.py`

Ovo je sloj za Redis naloge i glasanja.

Konstante:

```python
PENDING_ORDERS_KEY = "pending_orders"
ACTIVE_VOTES_KEY = "active_votes"
```

`order_key` i `vote_key` garantuju dosledna imena ključeva.

`add_order`:

1. generiše UUID;
2. dodaje UUID u objekat naloga;
3. pravi Redis pipeline sa `transaction=True`;
4. upisuje JSON i ZSET član;
5. izvršava obe operacije zajedno.

Pipeline sprečava stanje u kojem JSON postoji bez člana liste ili obrnuto.

`list_orders` čita UUID-eve i njihove JSON zapise. Ako ZSET sadrži UUID čiji JSON više ne postoji, taj zastareli član se uklanja.

`store_vote` radi analogno za aktivno glasanje.

`remove_order` i `remove_vote` takođe koriste pipeline da istovremeno uklone JSON ključ i ZSET član.

---

# 6. Auth servis

## `services/auth/models.py`

Definiše SQLAlchemy `User` model.

- `id` je primarni ključ;
- ime i prezime imaju do 256 znakova;
- email je obavezan, jedinstven i indeksiran;
- `password_hash` je duži string jer hash nije iste dužine kao lozinka;
- role je `employee` ili `director`, sa default vrednošću `employee`.

Indeks na email-u ubrzava login i proveru duplikata.

## `services/auth/init_db.py`

Ovaj modul pokreće Kubernetes SQL Job.

Početni direktor je definisan u konstanti `DIRECTOR`.

`initialize()`:

1. učita broj pokušaja i pauzu iz environmenta;
2. napravi Flask app da dobije DB konfiguraciju;
3. u app context-u pozove `db.create_all()`;
4. traži početnog direktora po email-u;
5. ako ne postoji, kreira ga i hash-uje lozinku;
6. ako postoji, samo osigurava da mu je role `director`;
7. commit-uje transakciju.

Ako MySQL još nije spreman, hvata `OperationalError`, ispisuje pokušaj, čeka i proba ponovo. Zato je nekoliko početnih `Connection refused` poruka normalno.

Inicijalizacija je idempotentna: ponovljeno pokretanje ne pravi drugog direktora.

## `services/auth/app.py`

Koristi Flask application factory `create_app`. To omogućava da produkcija koristi MySQL, a testovi proslede SQLite konfiguraciju.

### `normalized_email`

Prvo koristi jednostavan regex da odbije očigledno loše adrese, a zatim `email-validator` da normalizuje email. `check_deliverability=False` znači da se ne proverava internet/DNS domena. Email se pretvara u lowercase.

### `POST /register`

Redosled validacija je važan jer grader proverava tačne odgovore.

1. Provera nedostajućih polja redom: forename, surname, email, password.
2. Validacija email-a.
3. Ograničenja dužina i lozinke od najmanje 8 znakova.
4. Provera postojećeg korisnika.
5. Kreiranje employee korisnika sa hash-om.
6. Commit.

Postoji i `IntegrityError` zaštita. Dva paralelna zahteva mogu oba proći početni SELECT, ali database unique constraint i dalje sprečava duplikat. Tada se radi rollback.

### `POST /login`

Normalizuje email, nalazi korisnika i koristi `check_password_hash`. Ako je uspešno, pravi JWT:

- `identity` je email;
- dodatni claims su ime, prezime, email i role;
- token traje jedan sat.

### `POST /delete`

Zahteva JWT, iz token identity-ja uzima email, nalazi i briše korisnika.

### `GET /health`

Radi jednostavan upit ka MySQL-u. Kubernetes readiness probe ne smatra servis spremnim ako baza nije dostupna.

Na kraju fajla globalno `app = create_app()` postoji zato što Gunicorn importuje `services.auth.app:app`.

---

# 7. Employee servis

## Kreiranje aplikacije

`create_app` konfiguriše JWT i bira stvarni ili testni Mongo/Redis klijent. Klijenti se čuvaju i u `app.extensions`, što olakšava pregled i testiranje.

## `POST /search`

Endpoint počinje praznom listom `clauses`.

Filteri:

- `name` pravi case-insensitive escaped regex;
- `category` traži vrednost unutar MongoDB categories niza;
- `buying_date` znači da je kupovina posle zadatog datuma (`$gt`);
- `selling_date` zahteva da prodaja postoji i da je pre zadatog datuma (`$lt`);
- `info_filters` radi nad dinamičkim `info` poljima.

Podržani operatori su:

```text
eq, ne, gt, gte, lt, lte, in, nin
```

Oni se mapiraju na MongoDB operatore `$eq`, `$ne` itd.

`FIELD_PATH` regex dozvoljava bezbedne putanje poput:

```text
purity
origin.country
technical.rating.value
```

Ne dozvoljava `$` ili proizvoljne Mongo izraze, čime sprečava query injection.

Svi filteri ulaze u `$and`, pa dokument mora zadovoljiti svaki poslati uslov. Ako nema filtera, query je `{}` i vraća svu imovinu.

## `POST /create_buy_order`

Validira podatke i poziva `add_order`. Važna odbrambena rečenica:

> BUY endpoint pravi predlog u Redis-u; ne pravi imovinu u MongoDB dok blockchain glasanje nije odobreno.

## `POST /create_sell_order`

MongoDB ID mora biti validan ObjectId i dokument mora postojati. Tako se ne može predložiti prodaja nepostojeće imovine. Posle validacije pravi se SELL nalog u Redis-u.

## `GET /health`

Proverava i MongoDB i Redis. Ako bilo koji ne radi, vraća 503 i Kubernetes ne označava Pod kao Ready.

---

# 8. Director servis

## `valid_uuid`

Pokušava da parsira vrednost kao UUID, a zatim poredi normalizovanu vrednost. Time odbija proizvoljne Redis ključeve i loše formate.

## `GET /pending_orders`

Dozvoljen samo direktoru. Poziva `list_orders` i vraća:

```json
{"orders": [...]}
```

## `POST /decision`

Dozvoljen samo direktoru. Radi sledeće:

1. validira UUID;
2. proverava da nalog postoji;
3. validira listu glasača;
4. odbija duple adrese;
5. odbija paran broj glasača;
6. vraća postojeći ugovor ako je glasanje ranije već pokrenuto;
7. inače deploy-uje ugovor;
8. čuva metapodatke u Redis-u;
9. vraća tri transaction payload-a.

Neparan broj glasača nije dovoljan sam po sebi za izbegavanje svih teorijskih problema, ali uz majority threshold garantuje da jedna strana može dostići strogu većinu bez nerešenog konačnog rezultata.

## `GET /report`

Koristi MongoDB aggregation pipeline.

`$unwind` pretvara jednu imovinu sa više kategorija u po jedan pipeline zapis za svaku kategoriju. Zbog toga ista kupovina doprinosi statistici svake svoje kategorije.

`$group` grupiše po kategoriji:

- `spent` sabira sve buying_price vrednosti;
- `earned` sabira selling_price samo kada postoje i selling_date i selling_price.

`$sort` sortira prvo po zaradi opadajuće, zatim potrošnji rastuće i na kraju nazivu kategorije.

## `GET /health`

Proverava Mongo, Redis i Web3 vezu sa Ganache-om. Director nije Ready ako bilo koja od te tri zavisnosti nije dostupna.

---

# 9. Blockchain sloj

## `blockchain/Voting.sol`

Ugovor se zove `InvestmentVote`.

### Stanje

`director` i `threshold` su `immutable`: postavljaju se u konstruktoru i kasnije ne mogu da se promene.

Mappings:

- `allowedVoters[address]` govori da li adresa sme da glasa;
- `hasVoted[address]` sprečava dvostruko glasanje.

Brojači i status:

- `approveVotes`;
- `rejectVotes`;
- `ended`;
- `approved`;
- `vetoed`.

Sve su `public`, pa Solidity automatski generiše read-only getter funkcije.

### Konstruktor

Zahteva pozitivan neparan broj glasača. `msg.sender` postaje direktor. Prag se računa kao polovina plus jedan.

Petlja odbija zero adresu i duplikat. Zatim svaku adresu označava kao dozvoljenu.

### `votingActive`

Modifier proverava `!ended`. Donja crta `_` označava mesto na kojem se izvršava telo funkcije.

Pošto approve, reject i veto koriste ovaj modifier, nijedna akcija nije moguća posle završetka.

### `approve` i `reject`

Obe pozivaju privatnu `_castVote` funkciju sa različitim boolean argumentom.

`_castVote`:

1. proverava da je `msg.sender` dozvoljen;
2. proverava da nije već glasao;
3. postavlja `hasVoted` pre promene brojača;
4. povećava odgovarajući brojač;
5. emituje `VoteCast` event;
6. proverava prag;
7. po dostizanju praga postavlja završno stanje i emituje `VotingFinished`.

### `veto`

Pored aktivnog glasanja zahteva `msg.sender == director`. Postavlja ended i vetoed. Ne postavlja approved, pa ugovor nema poslovni efekat.

### Nema timeout-a

Glasanje u trenutnoj specifikaciji nema vremensko ograničenje. Ako nijedna strana ne dostigne prag i direktor ne uloži veto, ostaje aktivno.

## `blockchain/Voting.json`

Ovo je kompajlirani artifact. Najvažnija polja su:

- `abi` — opis funkcija, argumenata, event-a i tipova;
- `bytecode` — mašinski kod koji se šalje pri deploy-u;
- `contractName`, `source` i `compiler` — metapodaci.

Web3 ne deploy-uje `.sol` fajl direktno. Koristi ABI i bytecode iz JSON-a.

Ako izmeniš Solidity izvor, moraš ponovo kompajlirati artifact. U suprotnom bi dokumentacija/source govorili jedno, a deploy-ovani bytecode radio staru verziju.

## `services/director/blockchain.py`

`BlockchainGateway` izoluje Web3 detalje od Flask endpointa.

Konstruktor:

- povezuje se na `BLOCKCHAIN_URL`;
- učitava sender adresu;
- čita `Voting.json`;
- izdvaja ABI i bytecode.

`deploy(voters)`:

1. pretvara adrese u checksum oblik;
2. pravi contract factory;
3. poziva konstruktor;
4. šalje transakciju sa direktorove adrese;
5. čeka receipt;
6. proverava status;
7. vraća adresu novog ugovora.

`transaction_payloads` koristi ABI da enkoduje pozive approve, reject i veto. Payload sadrži samo podatke potrebne klijentu da pošalje transakciju.

`status` koristi read-only `.call()` da pročita tri statusa bez nove blockchain transakcije i bez trošenja gasa.

---

# 10. Contract checker

Fajl je `jobs/contract_checker.py`.

## `outcome_from_status`

Prioritetno proverava veto, pa approved, a sve ostalo završeno smatra rejected. Checker ovu funkciju poziva tek kada je `ended == true`.

## `apply_final_outcome`

Prvo pokušava da kreira `processed_votes` marker koristeći `$setOnInsert` i `upsert=True`.

To znači:

- ako dokument ne postoji, kreira se;
- ako već postoji, postojeća vrednost se ne prepisuje.

Ako marker već ima `applied: true`, funkcija odmah izlazi. To je idempotentnost: ponovljeno izvršavanje ne pravi duplu imovinu.

Za odobren BUY koristi `update_one` sa `vote_uuid` i `$setOnInsert`, pa čak i u slučaju ponavljanja postoji najviše jedan dokument za isto glasanje.

Za odobren SELL radi `$set` nad postojećim ObjectId dokumentom. Ponavljanje istih vrednosti je bezbedno.

REJECTED i VETOED samo dobijaju marker, bez promene assets kolekcije.

Na kraju marker dobija `applied: true`.

## Redis lock

Checker koristi:

```text
SET checker-lock:<uuid> <nasumični-token> NX EX 55
```

- `NX` znači postavi samo ako ključ ne postoji;
- `EX 55` daje lock-u rok od 55 sekundi;
- token identifikuje vlasnika lock-a.

Ako se dva checker-a preklapaju, samo jedan dobija lock.

`release_lock` koristi WATCH/MULTI:

1. posmatra lock ključ;
2. proverava da token još pripada njemu;
3. transakcijski ga briše;
4. ako se ključ u međuvremenu promeni, Redis daje WatchError i operacija se ponavlja.

Ovo sprečava proces da obriše tuđi noviji lock nakon što je njegov stari lock istekao.

## `check_contracts`

Prolazi kroz `active_votes`.

- Ako vote JSON nedostaje, uklanja zastareli ZSET član.
- Ako ne dobije lock, preskače taj UUID.
- Ako ugovor nije završen, ostavlja sve kako jeste.
- Ako jeste, primenjuje rezultat i briše order/vote Redis stanje.
- Lock uvek oslobađa u `finally` bloku, čak i ako se desi greška.

## `main`

Kreira stvarne Redis, Mongo i Web3 klijente.

`CHECK_ONCE=true` znači proveri jednom i završi. Tako radi Kubernetes CronJob.

`CHECK_ONCE=false` znači ostani u petlji i čekaj `CHECK_INTERVAL_SECONDS`. Tako privremeni profesorov checker radi na svake dve sekunde.

---

# 11. Dockerfile

Dockerfile koristi multi-stage targets, ali svi nasleđuju isti `base`.

## Base sloj

```dockerfile
FROM python:3.11-slim AS base
```

Environment:

- `PYTHONDONTWRITEBYTECODE=1` sprečava `.pyc` fajlove u image-u;
- `PYTHONUNBUFFERED=1` odmah šalje logove na stdout;
- `PYTHONPATH=/app` omogućava import paketa iz `/app`.

Zatim:

1. postavlja radni direktorijum `/app`;
2. kopira requirements;
3. instalira biblioteke;
4. kopira common, services, jobs i blockchain;
5. kreira neprivilegovanog `iep` korisnika;
6. prestaje da radi kao root.

## Četiri targeta

`auth`, `employee` i `director` koriste Gunicorn sa dva worker procesa. Svaki target menja samo modul koji Gunicorn importuje.

Sva tri kontejnera interno slušaju `0.0.0.0:5000`.

`checker` ne pokreće HTTP server. On izvršava:

```text
python -m jobs.contract_checker
```

Build komanda bira target:

```bash
docker build --target auth -t iep-auth:latest .
```

Tako iz jednog Dockerfile-a nastaju četiri image-a.

## `.dockerignore`

Sprečava slanje Git podataka, venv-a, testova, dokumentacije, cache-a i privremenih fajlova u Docker build context. Time build postaje manji i brži.

---

# 12. Kubernetes manifest `k8s/all.yaml`

Manifest sadrži više YAML dokumenata odvojenih sa `---`.

## Namespace

Svi resursi su u namespace-u `iep`. To ih odvaja od sistemskih resursa i omogućava pregled sa `-n iep`.

## ConfigMap i Secret

ConfigMap čuva nesenzitivnu konfiguraciju:

- adrese servisa;
- portove;
- ime baze;
- blockchain URL i sender;
- checker i SQL retry ponašanje.

Secret čuva lozinke, JWT secret, Mongo URI i Ganache mnemonic.

Kubernetes Secret nije automatski jaka enkripcija — vrednosti su uglavnom samo odvojene od obične konfiguracije. U produkciji bi se koristilo pravilno secret upravljanje.

`envFrom` ubacuje sve ključeve ConfigMap-a i Secret-a kao environment promenljive u kontejner.

## MySQL

MySQL ima Service i StatefulSet.

Service daje stabilno DNS ime `mysql` i port 3306.

StatefulSet je izabran jer baza ima stanje i stabilan identitet `mysql-0`. VolumeClaimTemplate pravi PVC od 1 GiB koji se montira na `/var/lib/mysql`.

Readiness probe koristi `mysqladmin ping`. Pod može biti `Running`, ali nije `Ready` dok baza stvarno ne prihvata konekcije.

## MongoDB

Isto koristi Service + StatefulSet + PVC. Stabilni Pod je `mongo-0`, podaci su u `/data/db`, a readiness probe izvršava Mongo ping.

## Redis

Redis je Deployment sa jednom replikom i Service-om. Readiness koristi `redis-cli ping`.

U ovoj verziji nema PVC jer Redis služi kao privremeno stanje.

## Ganache

Ganache je Deployment sa jednom replikom. Pokreće lokalni blockchain sa 20 naloga i fiksnim mnemonic-om, pa su adrese determinističke pri svakom čistom startu.

Service izlaže port 8545. Readiness probe proverava TCP port.

## SQL Job

`sql-init` je `batch/v1 Job`.

Koristi `iep-auth` image, ali umesto Gunicorn CMD-a eksplicitno pokreće:

```text
python -m services.auth.init_db
```

`restartPolicy: OnFailure` i `backoffLimit: 6` daju Kubernetesu mogućnost ponavljanja neuspešnog Pod-a. Unutrašnja Python retry petlja dodatno čeka MySQL.

Job je bolji od init logike u svakom auth Pod-u zato što se inicijalizacija jasno izvršava jednom i ima zaseban status.

## Auth Deployment i Service

Jedna replika koristi lokalni `iep-auth:latest` image. `imagePullPolicy: IfNotPresent` znači da se lokalni image koristi ako postoji.

Readiness poziva `/health` na internom portu 5000.

Service izlaže port 5000.

## Employee Deployment i Service

Ima tri replike. Employee je stateless HTTP servis: stanje nije u Pod-u već u MongoDB/Redis-u, pa više replika mogu paralelno obrađivati zahteve.

Service radi load balancing između tri Pod-a. Spoljašnji port je 5001, a targetPort unutar Pod-a 5000.

## Director Deployment i Service

Jedna replika. Spoljašnji port je 5002, targetPort 5000.

## Contract-checker CronJob

Raspored:

```text
*/1 * * * *
```

znači svakog minuta.

`concurrencyPolicy: Forbid` sprečava Kubernetes da pokrene novi Job ako prethodni još radi.

Čuvaju se poslednja tri uspešna i tri neuspešna Job-a. Zato u `kubectl get pods` vidiš nekoliko `Completed` checker Pod-ova.

CronJob koristi `iep-checker` i `CHECK_ONCE=true`, pa jedna instanca proveri stanje i izađe.

## Zašto resursi mogu krenuti paralelno

`kubectl apply` kreira sve resurse bez čekanja da prethodni završi. Zato SQL Job može pokušati konekciju pre nego što je MySQL spreman. Retry logika i readiness čekanja rešavaju taj problem.

---

# 13. Glavne skripte

Postoje Bash skripte za macOS/Linux i PowerShell skripte za Windows. Poslovna logika im je ista.

## `setup.sh` i `setup.ps1`

Ovo je jednokratna priprema dok postoji internet.

Skripta:

1. pronalazi koren projekta;
2. proverava da postoje Docker i kubectl;
3. proverava da Docker i Kubernetes rade;
4. preuzima tačno verzionisane infrastrukturne image-e;
5. gradi četiri aplikaciona image-a;
6. pravi zaseban grader venv;
7. instalira `setuptools==70.3.0`;
8. instalira profesorove requirements.

Setuptools je potreban jer profesorov stariji Web3 koristi `pkg_resources`. Fiksna verzija uklanja slučajnost između računara.

Windows skripta dodatno proverava da Docker koristi Linux containers i uklanja grader venv ako je kopiran sa drugog operativnog sistema.

## `start.sh` i `start.ps1`

Ovo su tanki wrapper-i. Ne sadrže Kubernetes logiku, već prosleđuju argumente odgovarajućoj skripti u `scripts/`.

Bash koristi `exec`, pa interni proces preuzima mesto wrapper procesa i njegov exit code.

PowerShell prosleđuje switch parametre i izlazi sa istim `$LASTEXITCODE`.

## `scripts/start_k8s.sh` i `.ps1`

Podržane opcije:

- bez opcije: koristi postojeće podatke i image-e;
- `--build` / `-Build`: ponovo gradi aplikacione image-e;
- `--clean` / `-Clean`: briše ceo `iep` namespace i njegove podatke.

Tok:

1. validira argumente i alate;
2. po potrebi briše namespace;
3. proverava da li sva četiri `iep-*` image-a postoje;
4. gradi ih ako nedostaju ili je tražen build;
5. primenjuje `k8s/all.yaml`;
6. restartuje aplikacione Deployment-e da novi Pod-ovi uzmu aktuelne image-e;
7. čeka MySQL, Mongo, Redis i Ganache readiness;
8. čeka završetak SQL Job-a;
9. čeka rollout sva tri API servisa;
10. ispisuje konačno stanje i URL-ove.

Zašto se Deployment restartuje: Kubernetes ne pravi automatski novi Pod kada lokalni image dobije isti tag `latest`. Rollout restart menja Pod template anotaciju i prisiljava novi Pod.

`set -Eeuo pipefail` u Bash skriptama znači:

- `-e`: prekini na neuspešnoj komandi;
- `-u`: greška za nepostojeću promenljivu;
- `-o pipefail`: pipeline pada ako bilo koja komanda padne;
- `-E`: ERR trap se nasleđuje u funkcijama/subshell-ovima.

## `test.sh` i `test.ps1`

Takođe su wrapper-i. Prosleđuju `--reset` / `-Reset` skripti za profesorov grader.

## `scripts/reset_k8s_test_data.sh` i `.ps1`

Resetuje samo testno stanje, bez rušenja servisa.

1. čeka baze;
2. briše `assets` i `processed_votes` iz MongoDB;
3. radi `FLUSHALL` u Redis-u;
4. iz MySQL-a briše sve korisnike osim početnog direktora;
5. restartuje Ganache da blockchain ponovo bude prazan i determinističan;
6. čeka Ganache rollout.

Ovo je potrebno jer profesorovi testovi imaju stateful redosled i očekuju čist početak.

## `scripts/run_professor_tests.sh` i `.ps1`

Ovo je najsloženija skripta.

### Priprema klastera

- Ako namespace ne postoji i tražen je reset, skripta pokreće clean start.
- Ako namespace postoji i tražen je reset, poziva reset test podataka.
- Ako nema grader venv-a, kreira ga i instalira zavisnosti.
- Proverava da modul `pkg_resources` postoji pomoću `importlib.util.find_spec`, bez samog uvoza modula. Time Windows PowerShell ne pretvara njegovo deprecation upozorenje sa `stderr` izlaza u fatalni `NativeCommandError`.

### Port-forward

Profesorov grader radi na host računaru, a servisi su u klasteru. Skripta proverava portove 5000, 5001, 5002 i 8545. Ako neki nije dostupan preko Docker Desktop LoadBalancer-a, pokreće `kubectl port-forward`.

PID-evi procesa se pamte da bi se na kraju ugasili.

### Privremeni brzi checker

Produkcioni CronJob radi jednom u minutu, a profesorovi testovi ne treba toliko da čekaju posle svakog glasanja. Zato skripta privremeno primenjuje `scripts/professor_grader_checker.yaml`.

To je Deployment koji izvršava isti `jobs.contract_checker`, ali sa:

```text
CHECK_ONCE=false
CHECK_INTERVAL_SECONDS=2
```

Dakle, ne menja poslovnu logiku — samo proverava češće tokom testova.

### Pytest komanda

Skripta profesorovom graderu prosleđuje:

- URL svakog servisa;
- isti JWT secret kao Kubernetes manifest;
- nazive uloga i role claim-a;
- da su uključeni autentikacija i blockchain;
- Ganache URL;
- čekanje servisa;
- putanju JSON izveštaja.

### Cleanup

Bash `trap` i PowerShell `finally` uvek pokušavaju da:

- obrišu privremeni grader checker;
- ugase port-forward procese;
- vrate radni direktorijum.

Zato pomoćni Deployment nije deo glavnog `k8s/all.yaml`.

## `scripts/e2e_demo.py`

Ovo je čitljiva end-to-end demonstracija, ne profesorov grader.

Scenario:

1. registruje demo employee-a;
2. prijavi employee-a i direktora;
3. uzme Ganache naloge;
4. kreira BUY nalog;
5. pokrene glasanje;
6. pošalje dva approve glasa od tri;
7. proveri da je dalje glasanje blokirano;
8. sačeka MongoDB upis;
9. kreira drugi BUY nalog;
10. proveri da employee ne može veto;
11. direktor šalje veto;
12. proveri da veto nalog nije postao imovina;
13. proveri report.

Funkcija `expect_revert` namerno očekuje Solidity revert poruku. Funkcije `wait_for_*` polling-om čekaju asinhroni checker.

Za pouzdanu demonstraciju servisi moraju biti dostupni na lokalnim portovima, a checker dovoljno brz. Profesorova test skripta privremeno pravi brzi checker; normalni CronJob može čekati do minut.

---

# 14. Requirements i Python okruženja

## `requirements.txt`

Produkcione biblioteke:

- Flask i Gunicorn za API;
- Flask-JWT-Extended za tokene;
- Flask-SQLAlchemy, SQLAlchemy, PyMySQL i cryptography za MySQL;
- email-validator;
- pymongo;
- redis;
- python-dateutil;
- requests;
- web3 i Ethereum tipovi.

Verzije su zaključane da bi ponašanje bilo ponovljivo.

## `requirements-dev.txt`

Prvo uključuje sve produkcione requirements preko:

```text
-r requirements.txt
```

Zatim dodaje pytest, coverage, fakeredis, mongomock i setuptools.

## Dva venv-a

Root `.venv` služi za razvoj i interne testove.

`professor_tests/iep_grader/.venv` služi isključivo profesorovom graderu, koji ima sopstvene verzije zavisnosti.

Odvajanje sprečava konflikt između modernih projektnih biblioteka i profesorovih fiksiranih starijih biblioteka.

Aktivan `(.venv)` u terminal promptu ne utiče na Docker kontejnere. Kontejner ima svoj Python i svoje pakete.

## `pytest.ini`

Podešava:

```text
testpaths = tests
addopts = -q
```

Obični `pytest` zato automatski pokreće interne testove tiho, a ne profesorov grader.

---

# 15. Interni testovi

Interni testovi su brzi i ne zahtevaju Docker/Kubernetes.

Pokretanje:

```bash
.venv/bin/python -m pytest -q tests
```

## `tests/conftest.py`

Definiše fixtures:

- `mongomock` umesto stvarnog MongoDB-a;
- `fakeredis` umesto stvarnog Redis-a;
- helper za JWT sa proizvoljnom ulogom;
- Authorization header helper.

## `tests/test_auth.py`

Koristi in-memory SQLite. Testira registraciju, duplikat, login, brisanje, redosled validacija i nedostajući JWT.

## `tests/test_employee.py`

Testira BUY validaciju i Redis upis, sve search filtere, SELL ObjectId proveru i zabranu pristupa direktoru employee rutama.

## `tests/test_director.py`

Koristi `FakeBlockchain`. Time se testira director poslovna logika bez stvarnog Ganache-a.

Testira tri transaction payload-a, veto payload, validacije i Mongo aggregation report.

## `tests/test_checker.py`

Direktno testira finalnu obradu:

- dva poziva za isti BUY prave samo jednu imovinu;
- veto nema efekat na assets;
- odobren SELL ažurira postojeću imovinu.

## `tests/test_contract_artifact.py`

Proverava da ABI sadrži approve/reject/veto/status funkcije, da bytecode nije prazan i da Solidity source ima ključne require zaštite.

Ovaj test ne kompajlira Solidity, ali otkriva očigledan nesklad ili nedostajući artifact.

---

# 16. Profesorov grader

Direktorijum `professor_tests/iep_grader` treba tretirati kao spoljašnji, originalni test paket. Ne menja se da bi testovi prošli.

Ima 98 testova i ukupno 179 bodova.

Grupe:

- `authentication_tests.py` — register, login, delete i JWT claim-ovi;
- `level0_tests.py` — employee search i BUY/SELL validacije;
- `level1_tests.py` — director pending orders, decision i report;
- `level2_tests.py` — kompletan BUY pa SELL odobreni tok;
- `level3_tests.py` — reject, napredni filteri, ugnježdeni info i složen report;
- `conftest.py` — CLI opcije, fixtures i konfiguracija;
- `utilities.py` — HTTP/Web3 pomoćne funkcije;
- `data.py` — ulazni i očekivani podaci;
- `test_grader.py` — sastavlja konačnu parametrizovanu test kolekciju.

`grade_report.json` je generisani rezultat i zato je u `.gitignore`.

Poslednja puna provera ovog projekta dala je:

```text
authentication: 49/49
level0:          27/27
level1:          25/25
level2:          29/29
level3:          49/49
TOTAL:          179/179
```

---

# 17. Ostali fajlovi

## `.gitignore`

Sprečava Git da prati venv, cache, IDE konfiguraciju, coverage, privremene build fajlove i generisane grader izveštaje.

## Prazni `__init__.py` fajlovi

Nalaze se u `common`, `jobs`, `services` i test paketima. Njihova uloga je da direktorijumi budu Python paketi. Nemaju poslovnu logiku.

## `README.md`

Kratak operativni ulaz u projekat: struktura, portovi i glavne komande.

## `docs/ODBRANA.md`

Sažetak arhitekture i kratka pitanja za ponavljanje pred odbranu.

## `docs/PROBLEMI_NA_ODBRANI.md`

Praktičan troubleshooting vodič sa statusima, komandama i popravkama.

## `docs/MODIFIKACIJA_REDIS_LOGGER.md`

Spreman obrazac za moguću modifikaciju sa dodatnim CronJob-om koji ispisuje Redis stanje.

---

# 18. Šta se tačno dešava kada pokreneš tri komande

## `./setup.sh`

```text
internet
   │
   ├── docker pull infrastrukturnih image-a
   ├── docker build četiri iep image-a
   └── pip install profesorovog gradera
```

Posle uspešnog setup-a normalni start i test mogu raditi bez interneta, pod uslovom da ne resetuješ Docker image store/Kubernetes klaster.

## `./start.sh --clean`

```text
obriši namespace
       │
       ▼
proveri/gradi image-e
       │
       ▼
kubectl apply all.yaml
       │
       ├── baze i infrastruktura
       ├── SQL Job
       ├── API Deployment-i
       └── CronJob
       │
       ▼
čekaj readiness i rollout
```

## `./test.sh --reset`

```text
očisti test podatke
       │
       ├── Mongo collections
       ├── Redis FLUSHALL
       ├── MySQL employee korisnici
       └── restart Ganache
       │
       ▼
otvori potrebne port-forward procese
       │
       ▼
pokreni privremeni checker na 2 sekunde
       │
       ▼
pokreni 98 profesorovih testova
       │
       ▼
obriši helper i ugasi port-forward
```

---

# 19. Važne razlike koje profesor može pitati

## Deployment vs StatefulSet

Deployment je za stateless procese kojima stabilno ime i lokalni disk nisu bitni. Zato ga koriste API servisi, Redis u ovoj postavci i Ganache.

StatefulSet daje stabilan identitet i volume vezan za repliku. Zato ga koriste MySQL i MongoDB.

## Job vs CronJob

Job izvršava konačan posao i završava. SQL inicijalizacija treba da se izvrši jednom.

CronJob pravi Job-ove po rasporedu. Contract checker treba da se izvršava svakog minuta.

## Pod vs Deployment

Pod je najmanja izvršna jedinica. Deployment upravlja Pod-ovima, održava željeni broj replika i radi rollout. Ne kreiramo gole API Pod-ove jer se ne bi automatski obnovili posle pada.

## Service vs Deployment

Deployment upravlja procesima. Service daje stabilnu mrežnu adresu i raspoređuje saobraćaj na odgovarajuće Pod-ove.

## Readiness vs Running

`Running` znači da kontejnerski proces postoji. `Ready` znači da je aplikacija sposobna da prima zahteve. Zato možeš kratko videti `Running 0/1`.

## Docker image vs container

Image je nepromenljivi šablon sa kodom i zavisnostima. Container je pokrenuta instanca image-a. Kubernetes Pod sadrži jedan ili više kontejnera.

## Redis persistence vs Mongo/MySQL persistence

MySQL i Mongo imaju PVC jer sadrže trajne poslovne podatke. Redis sadrži prolazni workflow state i u ovoj školskoj postavci nema PVC.

## Hash vs JWT

Hash lozinke služi da se originalna lozinka ne čuva. JWT služi da korisnik posle login-a dokaže identitet i ulogu bez slanja lozinke svakom servisu.

## ABI vs bytecode

ABI opisuje kako klijent komunicira sa ugovorom. Bytecode je kod koji Ethereum Virtual Machine izvršava.

## Blockchain transakcija vs `.call()`

Transakcija menja blockchain stanje, mora imati sender i receipt. `.call()` samo čita stanje i ne pravi novu transakciju.

## Idempotentnost

Operacija je idempotentna ako ponavljanje ne menja konačan rezultat posle prvog uspeha. Checker koristi `processed_votes`, `vote_uuid` upsert i bezbedan SELL `$set` da ponovljena obrada ne duplira poslovni efekat.

---

# 20. Kako da usmeno predstaviš projekat

Možeš početi ovako:

> Projekat je mikroservisna aplikacija investicionog fonda sa tri Flask servisa. Auth koristi MySQL za korisnike i JWT autentikaciju. Employee pretražuje MongoDB i pravi BUY/SELL predloge u Redis-u. Director za predlog deploy-uje Solidity ugovor na lokalnom Ganache blockchainu i vraća approve, reject i veto transakcije. Kubernetes CronJob periodično čita završeno stanje ugovora i idempotentno primenjuje rezultat u MongoDB, nakon čega čisti privremeno Redis stanje. SQL baza se inicijalizuje posebnim Kubernetes Job-om, a employee servis ima tri replike.

Ako te prekinu, ova izjava je dovoljno gusta da profesor sam izabere deo koji želi da pita.

---

# 21. Pitanja za samostalnu proveru

Probaj da odgovoriš bez gledanja.

1. Zašto BUY nalog ne ide odmah u MongoDB?
2. Koja četiri Redis ključa/obrasca koristi workflow?
3. Zašto se koriste i `pending_orders` ZSET i `order:<uuid>` string?
4. Zašto je broj glasača neparan?
5. Kako se računa threshold za 3, 5 i 7 glasača?
6. Ko postaje director unutar Solidity ugovora?
7. Zašto employee ne može poslati veto?
8. Šta tačno sprečava glasanje nakon veta?
9. Koja je razlika između approved false i vetoed true?
10. Kako checker sazna da je glasanje završeno?
11. Zašto blockchain sam ne ažurira MongoDB?
12. Šta se upisuje za odobren BUY, a šta za odobren SELL?
13. Zašto REJECTED i VETOED ne menjaju assets?
14. Šta sprečava duplu checker obradu?
15. Zašto Redis lock ima token i expiration?
16. Zašto je `Completed` ispravan status za checker Pod?
17. Zašto SQL init ima i Python retry i Kubernetes Job retry?
18. Zašto MySQL i Mongo koriste StatefulSet, a employee Deployment?
19. Kako tri employee Pod-a dele stanje?
20. Koja je razlika između Service port i targetPort?
21. Zašto svi API kontejneri mogu interno slušati port 5000?
22. Kada koristiš `start`, kada `--build`, a kada `--clean`?
23. Šta `test --reset` briše, a šta zadržava?
24. Zašto testovi koriste privremeni checker Deployment?
25. Zašto postoje dva Python venv-a?
26. Šta radi `setuptools==70.3.0` u grader venv-u?
27. Zašto `imagePullPolicy` nije `Always`?
28. Šta moraš uraditi ako promeniš `Voting.sol`?
29. Kako health endpoint utiče na readiness?
30. Koju komandu prvo koristiš za `CrashLoopBackOff`?

Ako možeš jasno odgovoriti na ovih 30 pitanja i nacrtati odobreni BUY tok, razumeš projekat dovoljno dobro za ozbiljnu odbranu.
