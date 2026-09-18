# Moguće modifikacije — MongoDB, MySQL i Redis upiti

Ovaj dokument je priprema za modifikacije koje profesor može zadati na odbrani. Primeri nisu unapred dodati u aplikaciju jer nisu deo trenutne specifikacije. Kada dobiješ konkretan zahtev, uzmeš odgovarajući primer, prilagodiš naziv endpointa i tačan format odgovora koji profesor traži, pa ponovo izgradiš image.

Najvažnije pravilo:

> Prvo precizno utvrdi šta profesor smatra „zaradom”: prodajnu cenu ili profit `selling_price - buying_price`.

U ovom dokumentu:

- **prodajna cena** = `selling_price`;
- **profit/zarada** = `selling_price - buying_price`;
- **prodata imovina** = dokument koji ima i `selling_date` i `selling_price`.

---

# 1. Šema podataka koju koristiš u upitima

MongoDB kolekcija `assets` izgleda približno ovako:

```json
{
  "_id": "ObjectId",
  "name": "AssetAlpha",
  "categories": ["Technology", "Finance"],
  "buying_price": 50000,
  "buying_date": "MongoDB Date",
  "selling_price": 75000,
  "selling_date": "MongoDB Date",
  "info": {
    "location": "Belgrade"
  }
}
```

Neprodata imovina nema `selling_price` i `selling_date`.

MySQL tabela `users` ima:

```text
id
forename
surname
email
password_hash
role
```

## Stvarne modifikacije koje su se pojavljivale na rokovima

Prema primerima koje si naveo, posebno nauči ova četiri zadatka:

1. pronaći nekretninu sa najvećim profitom;
2. izračunati sumu prodajnih cena po kategoriji;
3. izračunati ukupan broj prodatih proizvoda/imovine;
4. izračunati prosečnu zaradu prodate imovine.

Odgovarajući Mongo obrasci su:

```text
najveći profit:       $match → $set/$subtract → $sort → $limit
suma po kategoriji:   $match → $unwind → $group/$sum → $sort
ukupan broj prodatih: $match → $count
prosečna zarada:      $match → $group/$avg/$subtract
```

Prvi i četvrti zadatak su detaljno obrađeni u poglavljima 3 i 4. Drugi i treći imaju zasebne gotove primere u nastavku.

---

# 2. Kako razmišljati o MongoDB aggregation pipeline-u

Najčešće faze su:

| Faza | Uloga |
|---|---|
| `$match` | filtrira dokumente |
| `$set` / `$addFields` | izračunava novo privremeno polje |
| `$sort` | sortira rezultate |
| `$limit` | zadržava prvih N rezultata |
| `$project` | bira i preimenuje izlazna polja |
| `$group` | grupiše i računa sumu, prosek, minimum ili maksimum |
| `$unwind` | pretvara svaki element niza u poseban pipeline zapis |
| `$count` | broji dokumente |

Redosled je bitan. Za najveći profit logika je:

```text
1. pronađi prodate nekretnine
2. izračunaj profit
3. sortiraj opadajuće
4. uzmi prvu
5. oblikuj odgovor
```

---

# 3. Modifikacija: nekretnina sa najvećim profitom

Pretpostavka je da „nekretnina” znači imovina koja u `categories` sadrži tačnu vrednost `Real Estate`.

## Čist MongoDB upit

Uđi u Mongo shell:

```bash
kubectl exec -it mongo-0 -n iep -- \
  mongosh "mongodb://iep:iep-password@127.0.0.1:27017/investment_fund?authSource=admin"
```

Zatim:

```javascript
db.assets.aggregate([
  {
    $match: {
      categories: "Real Estate",
      selling_price: {$exists: true, $ne: null},
      selling_date: {$exists: true, $ne: null}
    }
  },
  {
    $set: {
      profit: {$subtract: ["$selling_price", "$buying_price"]}
    }
  },
  {
    $sort: {
      profit: -1,
      name: 1
    }
  },
  {$limit: 1},
  {
    $project: {
      _id: 0,
      id: {$toString: "$_id"},
      name: 1,
      categories: 1,
      buying_price: 1,
      selling_price: 1,
      profit: 1
    }
  }
])
```

Objašnjenje:

1. `$match` zadržava samo prodate nekretnine.
2. `$subtract` računa prodajnu minus kupovnu cenu.
3. `profit: -1` sortira od najvećeg profita ka najmanjem.
4. `name: 1` daje determinističan rezultat ako dve nekretnine imaju isti profit.
5. `$limit: 1` vraća samo najbolju.
6. `$project` uklanja interni ObjectId i pretvara ga u string `id`.

Ako zadatak traži najprofitabilniju imovinu bez obzira na kategoriju, ukloni:

```javascript
categories: "Real Estate",
```

Ako profesor traži samo imovinu koja je ostvarila pozitivan profit, posle `$set` dodaj:

```javascript
{$match: {profit: {$gt: 0}}}
```

Bez tog dodatnog filtera upit ispravno vraća najveći rezultat čak i kada su sve prodaje završile gubitkom.

## Flask endpoint u director servisu

Dodaje se unutar `create_app` funkcije u `services/director/app.py`, najbolje pre `/health` endpointa:

```python
    @app.get("/most_profitable_real_estate")
    @role_required("director")
    def most_profitable_real_estate():
        pipeline = [
            {
                "$match": {
                    "categories": "Real Estate",
                    "selling_price": {"$exists": True, "$ne": None},
                    "selling_date": {"$exists": True, "$ne": None},
                }
            },
            {
                "$set": {
                    "profit": {"$subtract": ["$selling_price", "$buying_price"]}
                }
            },
            {"$sort": {"profit": -1, "name": 1}},
            {"$limit": 1},
            {
                "$project": {
                    "_id": 0,
                    "id": {"$toString": "$_id"},
                    "name": 1,
                    "categories": 1,
                    "buying_price": 1,
                    "selling_price": 1,
                    "profit": 1,
                }
            },
        ]

        asset = next(database.assets.aggregate(pipeline), None)
        return jsonify(asset=asset), 200
```

Ako nema prodate nekretnine, odgovor je:

```json
{"asset": null}
```

Profesor može zahtevati drugačiji odgovor, na primer praznu listu ili status 404. Pipeline ostaje isti; menja se samo poslednji deo endpointa.

---

# 4. Modifikacija: prosečna zarada prodate imovine

Najlogičnije tumačenje zarade je:

```text
profit = selling_price - buying_price
```

## Čist MongoDB upit za prosečan profit

```javascript
db.assets.aggregate([
  {
    $match: {
      selling_price: {$exists: true, $ne: null},
      selling_date: {$exists: true, $ne: null}
    }
  },
  {
    $group: {
      _id: null,
      average_profit: {
        $avg: {$subtract: ["$selling_price", "$buying_price"]}
      },
      total_profit: {
        $sum: {$subtract: ["$selling_price", "$buying_price"]}
      },
      sold_assets: {$sum: 1}
    }
  },
  {
    $project: {
      _id: 0,
      average_profit: 1,
      total_profit: 1,
      sold_assets: 1
    }
  }
])
```

Iako zadatak traži samo prosek, korisno je tokom provere vratiti i broj dokumenata i ukupan profit. Ako profesor zahteva tačno samo jedno polje, ostavi samo `average_profit`.

## Flask endpoint

```python
    @app.get("/average_profit")
    @role_required("director")
    def average_profit():
        pipeline = [
            {
                "$match": {
                    "selling_price": {"$exists": True, "$ne": None},
                    "selling_date": {"$exists": True, "$ne": None},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "average_profit": {
                        "$avg": {
                            "$subtract": ["$selling_price", "$buying_price"]
                        }
                    },
                    "total_profit": {
                        "$sum": {
                            "$subtract": ["$selling_price", "$buying_price"]
                        }
                    },
                    "sold_assets": {"$sum": 1},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "average_profit": 1,
                    "total_profit": 1,
                    "sold_assets": 1,
                }
            },
        ]

        result = next(database.assets.aggregate(pipeline), None)
        if result is None:
            result = {
                "average_profit": None,
                "total_profit": 0,
                "sold_assets": 0,
            }
        return jsonify(result), 200
```

Matematički, prosečna vrednost praznog skupa ne postoji, pa primer vraća `null`. Ako profesor zahteva nulu, promeni samo:

```python
"average_profit": 0
```

## Ako profesor pod „zaradom” misli na prodajnu cenu

Tada ne oduzimaš buying price:

```javascript
db.assets.aggregate([
  {
    $match: {
      selling_price: {$exists: true, $ne: null},
      selling_date: {$exists: true, $ne: null}
    }
  },
  {
    $group: {
      _id: null,
      average_selling_price: {$avg: "$selling_price"}
    }
  },
  {$project: {_id: 0, average_selling_price: 1}}
])
```

Na odbrani pitaj:

> Da li pod prosečnom zaradom mislite na prosečnu prodajnu cenu ili prosečnu razliku prodajne i kupovne cene?

To nije izbegavanje zadatka, već preciziranje poslovne definicije.

---

# 5. Modifikacija: tri najprofitabilnije prodate imovine

```javascript
db.assets.aggregate([
  {
    $match: {
      selling_price: {$exists: true, $ne: null},
      selling_date: {$exists: true, $ne: null}
    }
  },
  {
    $set: {
      profit: {$subtract: ["$selling_price", "$buying_price"]}
    }
  },
  {$sort: {profit: -1, name: 1}},
  {$limit: 3},
  {
    $project: {
      _id: 0,
      name: 1,
      buying_price: 1,
      selling_price: 1,
      profit: 1
    }
  }
])
```

Python endpoint koristi isti pipeline:

```python
assets = list(database.assets.aggregate(pipeline))
return jsonify(assets=assets), 200
```

Razlika u odnosu na prethodni primer je samo `$limit: 3` i vraćanje cele liste.

---

# 6. Modifikacija: ukupna i prosečna zarada po kategoriji

Jedna imovina može pripadati većem broju kategorija. Zato prvo koristiš `$unwind`.

```javascript
db.assets.aggregate([
  {
    $match: {
      selling_price: {$exists: true, $ne: null},
      selling_date: {$exists: true, $ne: null}
    }
  },
  {
    $set: {
      profit: {$subtract: ["$selling_price", "$buying_price"]}
    }
  },
  {$unwind: "$categories"},
  {
    $group: {
      _id: "$categories",
      total_profit: {$sum: "$profit"},
      average_profit: {$avg: "$profit"},
      sold_assets: {$sum: 1}
    }
  },
  {$sort: {total_profit: -1, _id: 1}},
  {
    $project: {
      _id: 0,
      category: "$_id",
      total_profit: 1,
      average_profit: 1,
      sold_assets: 1
    }
  }
])
```

Važna posledica `$unwind` faze: ako imovina pripada kategorijama `Technology` i `Finance`, njen profit ulazi u statistiku obe kategorije. To je isto ponašanje koje postojeći `/report` koristi za buying/selling statistiku.

Ako profesor traži samo kategoriju sa najvećim ukupnim profitom, posle `$sort` dodaj:

```javascript
{$limit: 1}
```

---

# 7. Modifikacija: broj prodatih i neprodatih imovina

## Jedan rezultat sa dve vrednosti

```javascript
db.assets.aggregate([
  {
    $group: {
      _id: null,
      total_assets: {$sum: 1},
      sold_assets: {
        $sum: {
          $cond: [
            {
              $and: [
                {$ne: [{$ifNull: ["$selling_price", null]}, null]},
                {$ne: [{$ifNull: ["$selling_date", null]}, null]}
              ]
            },
            1,
            0
          ]
        }
      },
      unsold_assets: {
        $sum: {
          $cond: [
            {
              $and: [
                {$ne: [{$ifNull: ["$selling_price", null]}, null]},
                {$ne: [{$ifNull: ["$selling_date", null]}, null]}
              ]
            },
            0,
            1
          ]
        }
      }
    }
  },
  {$project: {_id: 0}}
])
```

Ovaj primer pokazuje `$cond`, odnosno MongoDB uslovni izraz.

## Stvarna modifikacija: ukupan broj prodatih proizvoda

Ako se traži samo jedan ukupan broj, ne treba ti složeni `$group`. Najčistiji aggregation pipeline je:

```javascript
db.assets.aggregate([
  {
    $match: {
      selling_price: {$exists: true, $ne: null},
      selling_date: {$exists: true, $ne: null}
    }
  },
  {$count: "sold_products"}
])
```

Primer rezultata:

```json
[{"sold_products": 5}]
```

Još kraća MongoDB varijanta je:

```javascript
db.assets.countDocuments({
  selling_price: {$exists: true, $ne: null},
  selling_date: {$exists: true, $ne: null}
})
```

Ako profesor izričito kaže „uradi kroz aggregation pipeline”, koristi `$match` + `$count`. Ako samo kaže „Mongo upit”, `countDocuments` je potpuno validan i jednostavniji.

Flask endpoint u director servisu:

```python
    @app.get("/sold_products_count")
    @role_required("director")
    def sold_products_count():
        count = database.assets.count_documents({
            "selling_price": {"$exists": True, "$ne": None},
            "selling_date": {"$exists": True, "$ne": None},
        })
        return jsonify(sold_products=count), 200
```

Ako koristiš isključivo aggregation:

```python
    @app.get("/sold_products_count")
    @role_required("director")
    def sold_products_count():
        pipeline = [
            {
                "$match": {
                    "selling_price": {"$exists": True, "$ne": None},
                    "selling_date": {"$exists": True, "$ne": None},
                }
            },
            {"$count": "sold_products"},
        ]
        result = next(database.assets.aggregate(pipeline), None)
        return jsonify(sold_products=result["sold_products"] if result else 0), 200
```

Važno: `$count` nad praznim skupom ne vraća dokument. Zato Python kod mora vratiti nulu kada je `result is None`.

---

# 7A. Stvarna modifikacija: suma cena prodatih proizvoda po kategoriji

Ovde se pod „cenom prodatog proizvoda” podrazumeva `selling_price`, ne profit.

## Čist MongoDB upit

```javascript
db.assets.aggregate([
  {
    $match: {
      selling_price: {$exists: true, $ne: null},
      selling_date: {$exists: true, $ne: null}
    }
  },
  {$unwind: "$categories"},
  {
    $group: {
      _id: "$categories",
      total_selling_price: {$sum: "$selling_price"},
      sold_products: {$sum: 1}
    }
  },
  {$sort: {_id: 1}},
  {
    $project: {
      _id: 0,
      category: "$_id",
      total_selling_price: 1,
      sold_products: 1
    }
  }
])
```

Primer rezultata:

```json
[
  {
    "category": "Finance",
    "total_selling_price": 175000,
    "sold_products": 2
  },
  {
    "category": "Real Estate",
    "total_selling_price": 300000,
    "sold_products": 2
  }
]
```

Objašnjenje:

1. `$match` izbacuje neprodate proizvode.
2. `$unwind` pravi poseban pipeline zapis za svaku kategoriju proizvoda.
3. `$group` grupiše po nazivu kategorije.
4. `$sum: "$selling_price"` sabira prodajne cene.
5. `$sum: 1` usput broji koliko je prodatih proizvoda doprinelo kategoriji.
6. `$project` preimenuje `_id` u čitljivije `category`.

Ako jedna imovina ima kategorije `Finance` i `Technology`, cela njena prodajna cena ulazi u sumu obe kategorije. To je isti princip koji koristi postojeći direktorov `/report` endpoint.

## Flask endpoint u director servisu

```python
    @app.get("/sold_prices_by_category")
    @role_required("director")
    def sold_prices_by_category():
        pipeline = [
            {
                "$match": {
                    "selling_price": {"$exists": True, "$ne": None},
                    "selling_date": {"$exists": True, "$ne": None},
                }
            },
            {"$unwind": "$categories"},
            {
                "$group": {
                    "_id": "$categories",
                    "total_selling_price": {"$sum": "$selling_price"},
                    "sold_products": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
            {
                "$project": {
                    "_id": 0,
                    "category": "$_id",
                    "total_selling_price": 1,
                    "sold_products": 1,
                }
            },
        ]

        statistics = list(database.assets.aggregate(pipeline))
        return jsonify(statistics=statistics), 200
```

Ako profesor traži samo sumu, bez broja proizvoda, ukloni:

```python
"sold_products": {"$sum": 1}
```

i odgovarajuće polje iz `$project`.

Ako traži sortiranje od kategorije sa najvećom sumom, promeni sort u:

```javascript
{$sort: {total_selling_price: -1, _id: 1}}
```

---

# 8. Modifikacija: najveći gubitak

Gubitak možeš predstaviti kao:

```text
loss = buying_price - selling_price
```

```javascript
db.assets.aggregate([
  {
    $match: {
      selling_price: {$exists: true, $ne: null},
      selling_date: {$exists: true, $ne: null},
      $expr: {$lt: ["$selling_price", "$buying_price"]}
    }
  },
  {
    $set: {
      loss: {$subtract: ["$buying_price", "$selling_price"]}
    }
  },
  {$sort: {loss: -1, name: 1}},
  {$limit: 1},
  {
    $project: {
      _id: 0,
      name: 1,
      buying_price: 1,
      selling_price: 1,
      loss: 1
    }
  }
])
```

`$expr` omogućava poređenje vrednosti dva polja istog dokumenta.

---

# 9. Modifikacija: prodata imovina u vremenskom periodu

MongoDB datumi treba da budu pravi Date objekti, ne stringovi.

```javascript
db.assets.find({
  selling_date: {
    $gte: ISODate("2026-01-01T00:00:00Z"),
    $lt: ISODate("2027-01-01T00:00:00Z")
  }
})
```

Aggregation sa ukupnim profitom perioda:

```javascript
db.assets.aggregate([
  {
    $match: {
      selling_date: {
        $gte: ISODate("2026-01-01T00:00:00Z"),
        $lt: ISODate("2027-01-01T00:00:00Z")
      },
      selling_price: {$exists: true, $ne: null}
    }
  },
  {
    $group: {
      _id: null,
      total_profit: {
        $sum: {$subtract: ["$selling_price", "$buying_price"]}
      },
      sold_assets: {$sum: 1}
    }
  },
  {$project: {_id: 0}}
])
```

U Flask endpointu datume iz requesta prvo parsiraj pomoću postojeće `parse_iso8601` funkcije, pa ih stavi u `$match` kao Python datetime objekte.

---

# 10. Modifikacija: grupisanje prodaje po mesecu

```javascript
db.assets.aggregate([
  {
    $match: {
      selling_date: {$exists: true, $ne: null},
      selling_price: {$exists: true, $ne: null}
    }
  },
  {
    $group: {
      _id: {
        year: {$year: "$selling_date"},
        month: {$month: "$selling_date"}
      },
      total_sales: {$sum: "$selling_price"},
      total_profit: {
        $sum: {$subtract: ["$selling_price", "$buying_price"]}
      },
      sold_assets: {$sum: 1}
    }
  },
  {$sort: {"_id.year": 1, "_id.month": 1}},
  {
    $project: {
      _id: 0,
      year: "$_id.year",
      month: "$_id.month",
      total_sales: 1,
      total_profit: 1,
      sold_assets: 1
    }
  }
])
```

---

# 11. Testni MongoDB podaci za vežbu

Nemoj unositi testne podatke neposredno pred profesorov grader. Koristi ih samo za vežbu, pa ih obriši.

U `mongosh`:

```javascript
db.assets.insertMany([
  {
    name: "MOD TEST House A",
    categories: ["Real Estate"],
    buying_price: 100000,
    buying_date: ISODate("2025-01-01T00:00:00Z"),
    selling_price: 160000,
    selling_date: ISODate("2026-01-01T00:00:00Z"),
    info: {city: "Belgrade"}
  },
  {
    name: "MOD TEST House B",
    categories: ["Real Estate"],
    buying_price: 120000,
    buying_date: ISODate("2025-02-01T00:00:00Z"),
    selling_price: 140000,
    selling_date: ISODate("2026-02-01T00:00:00Z"),
    info: {city: "Novi Sad"}
  },
  {
    name: "MOD TEST House C",
    categories: ["Real Estate"],
    buying_price: 90000,
    buying_date: ISODate("2025-03-01T00:00:00Z"),
    selling_price: 80000,
    selling_date: ISODate("2026-03-01T00:00:00Z"),
    info: {city: "Nis"}
  },
  {
    name: "MOD TEST Unsold",
    categories: ["Real Estate"],
    buying_price: 50000,
    buying_date: ISODate("2025-04-01T00:00:00Z"),
    info: {city: "Kragujevac"}
  }
])
```

Očekivanja:

- House A ima profit 60000 i najprofitabilnija je;
- House B ima profit 20000;
- House C ima profit -10000;
- prosečan profit prodatih nekretnina je `(60000 + 20000 - 10000) / 3`;
- Unsold ne sme da uđe u prodajne statistike.

Čišćenje samo ovih testnih zapisa:

```javascript
db.assets.deleteMany({name: /^MOD TEST/})
```

---

# 12. MySQL modifikacija: broj korisnika po ulozi

## Čist SQL

Uđi u MySQL:

```bash
kubectl exec -it mysql-0 -n iep -- /bin/sh
mysql -uiep -p"$MYSQL_PASSWORD" users
```

Upit:

```sql
SELECT role, COUNT(*) AS user_count
FROM users
GROUP BY role
ORDER BY role ASC;
```

## Flask/SQLAlchemy endpoint u auth servisu

Na vrh `services/auth/app.py` dodaj:

```python
from sqlalchemy import func
```

Postojeći security import promeni u:

```python
from common.security import configure_jwt, role_required
```

Unutar `create_app`, pre `/health`, dodaj:

```python
    @app.get("/user_statistics")
    @role_required("director")
    def user_statistics():
        rows = (
            db.session.query(User.role, func.count(User.id))
            .group_by(User.role)
            .order_by(User.role.asc())
            .all()
        )
        statistics = [
            {"role": role, "user_count": count}
            for role, count in rows
        ]
        return jsonify(statistics=statistics), 200
```

Ovaj endpoint pripada auth servisu jer on već poseduje MySQL konekciju i User model. Nemoj zbog ovog jednostavnog zadatka uvoditi MySQL konekciju u director servis, osim ako profesor izričito zahteva da ruta bude na director portu.

---

# 13. MySQL modifikacija: svi zaposleni sortirani po prezimenu

## SQL

```sql
SELECT id, forename, surname, email
FROM users
WHERE role = 'employee'
ORDER BY surname ASC, forename ASC, email ASC;
```

## SQLAlchemy

```python
    @app.get("/employees")
    @role_required("director")
    def employees():
        users = (
            User.query
            .filter_by(role="employee")
            .order_by(User.surname.asc(), User.forename.asc(), User.email.asc())
            .all()
        )
        return jsonify(employees=[
            {
                "id": user.id,
                "forename": user.forename,
                "surname": user.surname,
                "email": user.email,
            }
            for user in users
        ]), 200
```

Nikada ne vraćaj `password_hash` kroz API.

---

# 14. MySQL modifikacija: broj korisnika po email domenu

Ovo je MySQL-specifičan upit:

```sql
SELECT
  SUBSTRING_INDEX(email, '@', -1) AS domain,
  COUNT(*) AS user_count
FROM users
GROUP BY domain
ORDER BY user_count DESC, domain ASC;
```

Za zadatak pod vremenskim pritiskom, raw SQL možeš izvršiti kroz SQLAlchemy:

```python
from sqlalchemy import text
```

```python
    @app.get("/email_domain_statistics")
    @role_required("director")
    def email_domain_statistics():
        rows = db.session.execute(text("""
            SELECT
              SUBSTRING_INDEX(email, '@', -1) AS domain,
              COUNT(*) AS user_count
            FROM users
            GROUP BY domain
            ORDER BY user_count DESC, domain ASC
        """)).mappings().all()

        return jsonify(statistics=[dict(row) for row in rows]), 200
```

Raw SQL koristi samo kada je vrednost fiksna ili kada parametre prosleđuješ bezbednim bind parametrima. Nemoj sastavljati SQL direktnim ubacivanjem korisničkog inputa u string.

---

# 15. MySQL modifikacija: pretraga korisnika po delu imena

Ako endpoint prima query parametar `name`, koristi ORM da izbegneš SQL injection.

Na vrh dodaj:

```python
from sqlalchemy import or_
```

Endpoint:

```python
    @app.get("/users/search")
    @role_required("director")
    def search_users():
        value = request.args.get("name", "").strip()
        if not value:
            return jsonify(message="Field name is missing."), 400

        pattern = f"%{value}%"
        users = (
            User.query
            .filter(or_(
                User.forename.ilike(pattern),
                User.surname.ilike(pattern),
            ))
            .order_by(User.surname.asc(), User.forename.asc())
            .all()
        )

        return jsonify(users=[
            {
                "id": user.id,
                "forename": user.forename,
                "surname": user.surname,
                "email": user.email,
                "role": user.role,
            }
            for user in users
        ]), 200
```

---

# 16. Ako zadatak kaže „ispiši rezultat u log”

Tada endpoint možda uopšte nije potreban. Upit može izvršiti Kubernetes Job ili CronJob.

Primer jednokratnog Job-a koji ispisuje prosečan profit:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: mongo-profit-report
  namespace: iep
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: mongo-profit-report
          image: mongo:7.0.12
          command: ["/bin/sh", "-c"]
          args:
            - |
              mongosh "$MONGO_URI" --quiet --eval '
                const database = db.getSiblingDB("investment_fund");
                printjson(database.assets.aggregate([
                  {$match: {
                    selling_price: {$exists: true, $ne: null},
                    selling_date: {$exists: true, $ne: null}
                  }},
                  {$group: {
                    _id: null,
                    average_profit: {
                      $avg: {$subtract: ["$selling_price", "$buying_price"]}
                    }
                  }},
                  {$project: {_id: 0, average_profit: 1}}
                ]).toArray());
              '
          envFrom:
            - configMapRef:
                name: iep-config
            - secretRef:
                name: iep-secrets
```

Pokretanje i log:

```bash
kubectl apply -f k8s/mongo-profit-report.yaml
kubectl wait --for=condition=complete job/mongo-profit-report -n iep --timeout=120s
kubectl logs job/mongo-profit-report -n iep
```

Ako profesor traži isto svakog minuta, promeni `kind: Job` u CronJob strukturu i dodaj:

```yaml
spec:
  schedule: "*/1 * * * *"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        # ovde ide isti Pod spec
```

---

# 17. Kako primeniti Python modifikaciju

Ako si promenio `services/director/app.py` ili `services/auth/app.py`, postojeći Docker image i dalje sadrži star kod. Zato moraš uraditi rebuild.

macOS/Linux:

```bash
./start.sh --build
```

Windows:

```powershell
.\start.ps1 -Build
```

Skripta gradi image-e i restartuje auth/employee/director Deployment-e.

Provera:

```bash
kubectl rollout status deployment/director -n iep --timeout=300s
kubectl rollout status deployment/auth -n iep --timeout=300s
kubectl logs deployment/director -n iep --tail=100
kubectl logs deployment/auth -n iep --tail=100
```

Ako si dodao samo novi Kubernetes YAML, Python rebuild nije potreban:

```bash
kubectl apply -f k8s/IME_FAJLA.yaml
```

---

# 18. Kako brzo testirati novi endpoint

## Dobijanje director tokena

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:5000/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"onlymoney@gmail.com","password":"evenmoremoney"}' \
  | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')
```

Poziv Mongo endpointa:

```bash
curl -s http://127.0.0.1:5002/most_profitable_real_estate \
  -H "Authorization: Bearer $TOKEN"
```

Poziv MySQL endpointa na auth servisu:

```bash
curl -s http://127.0.0.1:5000/user_statistics \
  -H "Authorization: Bearer $TOKEN"
```

Na Windows PowerShell-u token možeš dobiti ovako:

```powershell
$Login = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:5000/login" `
  -ContentType "application/json" `
  -Body '{"email":"onlymoney@gmail.com","password":"evenmoremoney"}'

$Headers = @{ Authorization = "Bearer $($Login.accessToken)" }
Invoke-RestMethod -Uri "http://127.0.0.1:5002/most_profitable_real_estate" -Headers $Headers
```

---

# 19. Šta profesor najčešće proverava kod ovih modifikacija

Pre nego što kažeš da si završio, proveri:

1. Da li filtriraš samo prodate dokumente?
2. Da li je profit `selling_price - buying_price`, a ne obrnuto?
3. Da li kategorija koristi tačnu vrednost `Real Estate`?
4. Da li `$sort: {profit: -1}` znači opadajući redosled?
5. Da li si dodao `$limit: 1` za jedan rezultat?
6. Da li ObjectId pretvaraš u string pre JSON odgovora?
7. Šta endpoint vraća kada nema rezultata?
8. Da li endpoint zahteva director ulogu?
9. Da li je format odgovora tačno onakav kakav je profesor zadao?
10. Da li si posle Python izmene uradio `start --build`?
11. Da li si pogledao log novog Pod-a?
12. Da li si uklonio privremene ručno ubačene testne podatke?

---

# 20. Najkraći šabloni koje treba zapamtiti

## Najveća vrednost izraza

```javascript
[
  {$match: {/* uslovi */}},
  {$set: {result: {$subtract: ["$selling_price", "$buying_price"]}}},
  {$sort: {result: -1}},
  {$limit: 1},
  {$project: {_id: 0, name: 1, result: 1}}
]
```

## Prosek izraza

```javascript
[
  {$match: {/* uslovi */}},
  {$group: {
    _id: null,
    average: {$avg: {$subtract: ["$selling_price", "$buying_price"]}}
  }},
  {$project: {_id: 0, average: 1}}
]
```

## Grupisanje po elementu niza

```javascript
[
  {$unwind: "$categories"},
  {$group: {_id: "$categories", total: {$sum: 1}}},
  {$sort: {total: -1}}
]
```

## MySQL grupisanje

```sql
SELECT kolona, COUNT(*)
FROM tabela
WHERE uslov
GROUP BY kolona
ORDER BY COUNT(*) DESC;
```

Ako razumeš ova četiri obrasca, većinu kratkih modifikacija sa baze možeš sastaviti na licu mesta.

---

# 21. Redis komande za ovaj projekat

Redis čuva privremene BUY/SELL naloge, aktivna glasanja i kratkotrajne checker lock-ove.

## Ulazak u Redis CLI

```bash
kubectl exec -it deployment/redis -n iep -- redis-cli
```

Provera veze i izlazak:

```redis
PING
QUIT
```

`PING` treba da vrati `PONG`.

## Struktura Redis podataka

```text
pending_orders          Sorted Set UUID-eva naloga
order:<uuid>            String sa JSON BUY/SELL naloga

active_votes            Sorted Set UUID-eva aktivnih glasanja
vote:<uuid>             String sa JSON metapodataka glasanja

checker-lock:<uuid>     Privremeni String lock sa expiration vremenom
```

Sorted Set score je vreme nastanka. Zbog toga Redis može vratiti UUID-eve od najstarijeg ka najnovijem.

---

# 22. Osnovne komande za pregled

```redis
DBSIZE
INFO memory
INFO clients
INFO keyspace
```

- `DBSIZE` vraća ukupan broj ključeva;
- `INFO memory` prikazuje potrošnju memorije;
- `INFO clients` prikazuje povezane klijente;
- `INFO keyspace` prikazuje broj ključeva po Redis bazi.

Za ovaj mali lokalni projekat možeš koristiti:

```redis
KEYS *
KEYS order:*
KEYS vote:*
KEYS checker-lock:*
```

U produkciji se `KEYS *` izbegava jer može blokirati Redis. Bezbedniji obrazac je:

```redis
SCAN 0 MATCH order:* COUNT 100
SCAN 0 MATCH vote:* COUNT 100
SCAN 0 MATCH checker-lock:* COUNT 100
```

Provera tipa i postojanja ključa:

```redis
TYPE pending_orders
TYPE order:NEKI_UUID
EXISTS pending_orders
EXISTS order:NEKI_UUID
```

Očekivani tipovi:

```text
pending_orders  → zset
order:<uuid>    → string
active_votes    → zset
vote:<uuid>     → string
```

---

# 23. Pending BUY/SELL nalozi

## Svi UUID-evi od najstarijeg ka najnovijem

```redis
ZRANGE pending_orders 0 -1
```

Sa timestamp score vrednostima:

```redis
ZRANGE pending_orders 0 -1 WITHSCORES
```

## Ukupan broj naloga na čekanju

```redis
ZCARD pending_orders
```

## Najstariji i najnoviji nalog

```redis
ZRANGE pending_orders 0 0 WITHSCORES
ZREVRANGE pending_orders 0 0 WITHSCORES
```

## Konkretan JSON naloga

```redis
GET order:OVDE_UUID
```

BUY zapis sadrži:

```text
uuid, order_type, name, categories, buying_price, info
```

SELL zapis sadrži:

```text
uuid, order_type, id MongoDB imovine, selling_price
```

---

# 24. Ispis svih pending naloga

Prvo otvori shell u Redis kontejneru:

```bash
kubectl exec -it deployment/redis -n iep -- /bin/sh
```

Zatim:

```sh
for uuid in $(redis-cli ZRANGE pending_orders 0 -1); do
  echo "=== order:$uuid ==="
  redis-cli --raw GET "order:$uuid"
done
```

UUID-evi su u Sorted Set-u, a konkretan JSON u posebnim String ključevima. Zato su potrebna oba koraka.

Standardni Redis ne može jednostavno filtrirati polja unutar JSON stringa. Za ispis samo BUY naloga možeš koristiti Python u director Pod-u:

```bash
kubectl exec -it deployment/director -n iep -- python -c '
from common.clients import create_redis_client
from common.orders import list_orders
orders = list_orders(create_redis_client())
print([order for order in orders if order.get("order_type") == "BUY"])
'
```

Broj BUY i SELL naloga:

```bash
kubectl exec -it deployment/director -n iep -- python -c '
from collections import Counter
from common.clients import create_redis_client
from common.orders import list_orders
orders = list_orders(create_redis_client())
print(dict(Counter(order.get("order_type") for order in orders)))
'
```

---

# 25. Aktivna glasanja

```redis
ZRANGE active_votes 0 -1
ZRANGE active_votes 0 -1 WITHSCORES
ZCARD active_votes
ZRANGE active_votes 0 0 WITHSCORES
```

Metapodaci konkretnog glasanja:

```redis
GET vote:OVDE_UUID
```

Vote JSON sadrži:

```text
uuid
contract_address
director_address
voters
order
```

Ispis svih aktivnih glasanja iz shell-a Redis kontejnera:

```sh
for uuid in $(redis-cli ZRANGE active_votes 0 -1); do
  echo "=== vote:$uuid ==="
  redis-cli --raw GET "vote:$uuid"
done
```

---

# 26. Checker lock-ovi

```redis
SCAN 0 MATCH checker-lock:* COUNT 100
GET checker-lock:OVDE_UUID
TTL checker-lock:OVDE_UUID
```

TTL rezultat znači:

```text
pozitivan broj  → preostale sekunde
-1              → ključ postoji, ali nema expiration
-2              → ključ ne postoji
```

Checker pravi lock sa `NX EX 55`, pa njegov TTL treba da bude najviše 55 sekundi.

---

# 27. Praćenje Redis saobraćaja uživo

U posebnom terminalu:

```bash
kubectl exec -it deployment/redis -n iep -- redis-cli MONITOR
```

Dok praviš BUY/SELL nalog ili pokrećeš glasanje, videćeš komande poput:

```text
SET order:<uuid> ...
ZADD pending_orders ...
GET order:<uuid>
SET vote:<uuid> ...
ZADD active_votes ...
DEL order:<uuid>
ZREM pending_orders <uuid>
```

Za izlaz koristi `Ctrl+C`. `MONITOR` koristi samo kratko u lokalnom okruženju jer prikazuje sav Redis saobraćaj.

---

# 28. Komande koje menjaju Redis podatke

Koristi ih samo kada namerno testiraš ili popravljaš određeni zapis.

```redis
SET primer "vrednost"
GET primer
DEL primer

ZADD pending_orders 1234567890 "NEKI_UUID"
ZREM pending_orders "NEKI_UUID"
```

Ručno uklanjanje kompletnog naloga zahteva brisanje obe strukture:

```redis
DEL order:OVDE_UUID
ZREM pending_orders OVDE_UUID
```

Za glasanje analogno:

```redis
DEL vote:OVDE_UUID
ZREM active_votes OVDE_UUID
```

Ako obrišeš samo jednu polovinu, dobijaš stale stanje.

Opasna komanda:

```redis
FLUSHALL
```

`FLUSHALL` briše sve Redis ključeve. Projektna `test --reset` skripta je koristi namerno, ali je nemoj kucati tokom obične demonstracije.

---

# 29. Moguće Redis modifikacije na odbrani

## Broj pending naloga

```redis
ZCARD pending_orders
```

Python:

```python
count = cache.zcard("pending_orders")
```

## Broj aktivnih glasanja

```redis
ZCARD active_votes
```

```python
count = cache.zcard("active_votes")
```

## Najstariji pending nalog

```python
import json

result = cache.zrange("pending_orders", 0, 0)
order = None
if result:
    raw = cache.get(f"order:{result[0]}")
    order = json.loads(raw) if raw else None
```

## Svi pending nalozi

U projektu već postoji helper:

```python
from common.orders import list_orders

orders = list_orders(cache)
```

## Flask endpoint sa Redis statistikom

Dodaje se u director servis, koji već ima `cache` klijent:

```python
    @app.get("/redis_statistics")
    @role_required("director")
    def redis_statistics():
        return jsonify(
            pending_orders=cache.zcard("pending_orders"),
            active_votes=cache.zcard("active_votes"),
        ), 200
```

Posle izmene Python koda:

```bash
./start.sh --build
```

Windows:

```powershell
.\start.ps1 -Build
```

---

# 30. Redis komande koje treba zapamtiti

```redis
PING
DBSIZE
TYPE key
EXISTS key
GET key
DEL key
SCAN 0 MATCH pattern COUNT 100

ZRANGE pending_orders 0 -1 WITHSCORES
ZREVRANGE pending_orders 0 0 WITHSCORES
ZCARD pending_orders
ZREM pending_orders uuid

ZRANGE active_votes 0 -1 WITHSCORES
ZCARD active_votes

TTL checker-lock:uuid
MONITOR
```

Najvažnije za ovaj projekat:

```text
ZSET daje UUID-eve i redosled.
GET daje konkretan JSON.
ZCARD daje broj stavki.
```
