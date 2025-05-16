

import random
import string

def random_hex_string(length=32):
    return ''.join(random.choices(string.hexdigits, k=length)).lower()

"""
INSERT INTO aka_name (id, person_id, name, imdb_index, name_pcode_cf, name_pcode_nf, surname_pcode, md5sum)
VALUES (id, person_id, name, imdb_index, name_pcode_cf, name_pcode_nf, surname_pcode, md5sum);

901343
4061926
"""
def generate_aka_name(n, lastId, lastPerson_id):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        lastPerson_id +=1
        person_id = str(lastPerson_id)
        name =  "'" + random_hex_string(5) + " " + random_hex_string(5) + " " + random_hex_string(5) + "'"
        imdb_index = "NULL"
        name_pcode_cf = "'T357'"
        name_pcode_nf = "'T357'"
        surname_pcode = "'T357'"
        md5sum = "'" + random_hex_string() + "'"

        row = "(" + id + ", " + person_id + ", " + name + ", " + imdb_index + ", " + name_pcode_cf + ", "
        row = row + name_pcode_nf + ", " + surname_pcode + ", " + md5sum + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO aka_title (id, movie_id, title, imdb_index, kind_id, production_year, phonetic_code, episode_of_id, season_nr, episode_nr, note, md5sum)
VALUES (id, movie_id, title, imdb_index, kind_id, production_year, phonetic_code, episode_of_id, season_nr, episode_nr, note, md5sum);

377960
2528312
"""
def generate_aka_title(n, lastId, lastMovie_id):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        lastMovie_id += 1
        movie_id = str(lastMovie_id)
        title = "'" + random_hex_string(20) + "'"
        imdb_index = "NULL"
        kind_id = str(random.randint(1, 7))
        production_year = str(random.randint(1940, 2025))
        phonetic_code = "'T357'"
        episode_of_id = "NULL"
        season_nr = "NULL"
        episode_nr = "NULL"
        note = "NULL"
        md5sum = "'" + random_hex_string() +"'"

        row = "(" + id + ", " + movie_id + ", " + title + ", " + imdb_index + ", " + kind_id + ", "
        row = row + production_year + ", " + phonetic_code + ", " + episode_of_id + ", "
        row = row + season_nr + ", " + episode_nr + ", " + note + ", " + md5sum + ")"
        #print(row)
        values.append(row)
    return values

"""
INSERT INTO cast_info (id, person_id, movie_id, person_role_id, note, nr_order, role_id)
VALUES (id, person_id, movie_id, person_role_id, note, nr_order, role_id);

36244344
4061926 
2528312
"""
def generate_cast_info(n, lastId, lastPerson_id, lastMovie_id):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        lastPerson_id +=1
        person_id = str(lastPerson_id)
        lastMovie_id += 1
        movie_id = str(lastMovie_id)
        person_role_id = "NULL"
        note = "NULL"
        nr_order = "NULL"
        role_id = str(random.randint(1, 11))

        row = "(" + id + ", " + person_id + ", " + movie_id + ", " + person_role_id + ", " + note + ", "
        row = row + nr_order + ", " + role_id + ")"

        #print(row)
        values.append(row)
    return values


"""
INSERT INTO char_name (id, name, imdb_index, imdb_id, name_pcode_nf, surname_pcode, md5sum)
VALUES (id, name, imdb_index, imdb_id, name_pcode_nf, surname_pcode, md5sum);

3140339
"""
def generate_char_name(n, lastId):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        name = "'" + random_hex_string(5) + " " + random_hex_string(5) + "'"
        imdb_index = "NULL"
        imdb_id = "NULL"
        name_pcode_nf = "'T357'"
        surname_pcode = "'T357'"
        md5sum = "'" + random_hex_string() + "'"

        row = "(" + id + ", " + name + ", " + imdb_index + ", " + imdb_id + ", " + name_pcode_nf + ", "
        row = row + surname_pcode + ", " + md5sum + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO comp_cast_type (id, kind)
VALUES (id, kind);

4
"""
def generate_comp_cast_type(n, lastId):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        kind = "'" + random_hex_string(32) + "'"

        row = "(" + id + ", " + kind + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO company_name (id, name, country_code, imdb_id, name_pcode_nf, name_pcode_sf, md5sum)
VALUES (id, name, country_code, imdb_id, name_pcode_nf, name_pcode_sf, md5sum);

234997
"""
def generate_company_name(n, lastId):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        name = "'" + random_hex_string(5) + "'"
        country_code = "'["+random_hex_string(2)+"]'" 
        imdb_id = "NULL"
        name_pcode_nf = "'T357'"
        name_pcode_sf = "'T357'"
        md5sum = "'" + random_hex_string() + "'"

        row = "(" + id + ", " + name  + ", " + country_code  + ", " + imdb_id  + ", " + name_pcode_nf  + ", " + name_pcode_sf  + ", " + md5sum + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO company_type (id, kind)
VALUES (id, kind);

4
"""
def generate_company_type(n, lastId):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        kind = "'" + random_hex_string(32) + "'"

        row = "(" + id + ", " + kind + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO complete_cast (id, movie_id, subject_id, status_id)
VALUES (id, movie_id, subject_id, status_id);

135086
2528312
"""
def generate_complete_cast(n, lastId, lastMovie_id):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        lastMovie_id += 1
        movie_id = str(lastMovie_id)
        subject_id = str(random.randint(1, 2))
        status_id = str(random.randint(3, 4))

        row = "(" + id + ", " + movie_id  + ", " + subject_id + ", " + status_id  + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO info_type (id, info)
VALUES (id, info);

113
"""
def generate_info_type(n, lastId):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        info = "'" + random_hex_string(32) + "'"

        row = "(" + id + ", " + info + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO keyword (id, keyword, phonetic_code)
VALUES (id, keyword, phonetic_code);

134170
"""
def generate_keyword(n, lastId):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        keyword = "'" + random_hex_string(5) + "-" + random_hex_string(5) + "'"
        phonetic_code = "'T357'"

        row = "(" + id + ", " + keyword + ", " + phonetic_code + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO kind_type (id, kind)
VALUES (id, kind);

7
"""
def generate_kind_type(n, lastId):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        kind = "'" + random_hex_string(15) +"'"

        row = "(" + id + ", " + kind + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO link_type (id, link)
VALUES (id, link);

18
"""
def generate_link_type(n, lastId):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        link = "'" + random_hex_string(32) +"'"

        row = "(" + id + ", " + link + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO movie_companies (id, movie_id, company_id, company_type_id, note)
VALUES (id, movie_id, company_id, company_type_id, note);

2609129
2528312
234997
"""
def generate_movie_companies(n, lastId, lastMovie_id, lastCompany_id):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        lastMovie_id += 1
        movie_id = str(lastMovie_id)
        lastCompany_id += 1
        company_id = str(lastCompany_id)
        company_type_id = str(random.randint(1, 2))
        note = "NULL"

        row = "(" + id + ", " + movie_id + ", " + company_id + ", " + company_type_id + ", " + note + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO movie_info (id, movie_id, info_type_id, info, note)
VALUES (id, movie_id, info_type_id, info, note);

14835720
2528312 
"""
def generate_movie_info(n, lastId, lastMovie_id):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        lastMovie_id += 1
        movie_id = str(lastMovie_id)
        info_type_id = str(random.randint(1, 110))
        company_tyinfoe_id = "'" + random_hex_string(20) +"'"
        note = "NULL"

        row = "(" + id + ", " + movie_id + ", " + info_type_id + ", " + company_tyinfoe_id + ", " + note + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO movie_info_idx (id, movie_id, info_type_id, info, note)
VALUES (id, movie_id, info_type_id, info, note);

1380035
2528312
"""
def generate_movie_info_idx(n, lastId, lastMovie_id):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        lastMovie_id += 1
        movie_id = str(lastMovie_id)
        info_type_id = str(random.randint(99, 113))
        company_tyinfoe_id = "'" + "".join([str(random.randint(0, 9)) for i in range(random.randint(10, 20))]) + "'"
        note = "NULL"

        row = "(" + id + ", " + movie_id + ", " + info_type_id + ", " + company_tyinfoe_id + ", " + note + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO movie_keyword (id, movie_id, keyword_id)
VALUES (id, movie_id, keyword_id);

4523930
2528312
134170
"""
def generate_movie_keyword(n, lastId, lastMovie_id, lastKeyword_id):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        lastMovie_id += 1
        movie_id = str(lastMovie_id)
        lastKeyword_id += 1
        keyword_id = str(lastKeyword_id)

        row = "(" + id + ", " + movie_id + ", " + keyword_id + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO movie_link (id, movie_id, linked_movie_id, link_type_id)
VALUES (id, movie_id, linked_movie_id, link_type_id);

29997
2528312
2524994

"""
def generate_movie_link(n, lastId, lastMovie_id,  lastLinked_movie_id):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        lastMovie_id += 1 
        movie_id = str(lastMovie_id)
        lastLinked_movie_id += 1
        linked_movie_id = str(lastLinked_movie_id)
        link_type_id = str(random.randint(1, 17))

        row = "(" + id + ", " + movie_id + ", " + linked_movie_id + ", " + link_type_id + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO name (id, name, imdb_index, imdb_id, gender, name_pcode_cf, name_pcode_nf, surname_pcode, md5sum)
VALUES (id, name, imdb_index, imdb_id, gender, name_pcode_cf, name_pcode_nf, surname_pcode, md5sum);

4167491
"""
def generate_name(n, lastId):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        name = "'" + random_hex_string(10) + " " + random_hex_string(10) +"'"
        imdb_index = "NULL"
        imdb_id = "NULL"
        gender = "NULL"
        name_pcode_cf = "'T357'"
        name_pcode_nf = "'T357'"
        surname_pcode = "'T357'"
        md5sum = "'" + random_hex_string() + "'"

        row = "(" + id + ", " + name + ", " + imdb_index + ", " + imdb_id + ", " + gender + ", "
        row = row + name_pcode_cf + ", " + name_pcode_nf + ", " + surname_pcode + ", "  + md5sum + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO person_info (id, person_id, info_type_id, info, note)
VALUES (id, person_id, info_type_id, info, note);

2963664
4061926
"""
def generate_person_info(n, lastId, lastPerson_id):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        lastPerson_id += 1
        person_id = str(lastPerson_id)
        info_type_id = str(random.randint(15, 39))
        info = "'" + random_hex_string(300) + "'"
        note = "NULL"

        row = "(" + id + ", " + person_id + ", " + info_type_id + ", " + info + ", " + note + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO role_type (id, role)
VALUES (id, role);

12
"""
def generate_role_type(n, lastId):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        role = "'" + random_hex_string(32) + "'"

        row = "(" + id + ", " + role + ")"

        #print(row)
        values.append(row)
    return values

"""
INSERT INTO title (id, title, imdb_index, kind_id, production_year, imdb_id, phonetic_code, episode_of_id, season_nr, episode_nr, series_years, md5sum)
VALUES (2528313, 'Movie Test', NULL, 1, 2025, NULL, 'T357', NULL, NULL, NULL, NULL, '8dff29456328dee2h2756f9618cf2dbf');

2528312
"""
def generate_title(n, lastId):
    values = []
    for i in range(n):
        row = ""
        lastId +=1
        id = str(lastId)
        title = "'" + str(random_hex_string(10)) + " " + str(lastId) + "'"
        imdb_index = "NULL"
        kind_id = str(random.randint(1, 7)) 
        production_year = str(random.randint(1940, 2025))
        imdb_id = "NULL"
        phonetic_code = "'T357'"
        episode_of_id = "NULL"
        season_nr = "NULL"
        episode_nr = "NULL"
        series_years = "NULL"
        md5sum = "'" + random_hex_string() + "'"

        row = "(" + id + ", " + title + ", " + imdb_index + ", " + kind_id + ", " + production_year + ", "
        row = row + imdb_id + ", " + phonetic_code + ", " + episode_of_id + ", " + season_nr + ", "
        row = row + episode_nr + ", " + series_years + ", " + md5sum + ")"

        #print(row)
        values.append(row)
    return values


tab_aka_name = generate_aka_name(133, 901343, 4167489)
tab_aka_title = generate_aka_title(133, 377960, 2528312)
tab_cast_info = generate_cast_info(133, 36244344, 4061926, 2528312)
tab_char_name = generate_char_name(133, 3140339)
tab_comp_cast_type = generate_comp_cast_type(0, 4)
tab_company_name = generate_company_name(133, 234997)
tab_company_type = generate_company_type(0, 4)
tab_complete_cast = generate_complete_cast(133, 135086, 2528312)
tab_info_type = generate_info_type(0, 113)
tab_keyword = generate_keyword(133, 134170)
tab_kind_types = generate_kind_type(0, 7)
tab_link_types = generate_link_type(0, 18)
tab_movie_companies = generate_movie_companies(133, 2609129, 2528312, 234997)
tab_movie_info = generate_movie_info(133, 14835720, 2528312)
tab_info_idx = generate_movie_info_idx(133, 1380035, 2528312)
tab_movie_keyword = generate_movie_keyword(134, 4523930, 2528312, 134170)
tab_movie_link = generate_movie_link(134, 29997, 2528312,  2524994)
tab_name = generate_name(134, 4167491)
tab_person_info = generate_person_info(134, 2963664, 4061926)
tab_role_type = generate_role_type(0, 12)
tab_title = generate_title(134, 2528312)

numberOfQueries = len(tab_aka_name) + len(tab_aka_title) + len(tab_cast_info) + len(tab_char_name) + len(tab_comp_cast_type)
numberOfQueries += len(tab_company_name) + len(tab_company_type) + len(tab_complete_cast) + len(tab_info_type) + len(tab_keyword)
numberOfQueries += len(tab_kind_types) + len(tab_link_types) + len(tab_movie_companies) + len(tab_movie_info) + len(tab_info_idx)
numberOfQueries += len(tab_movie_keyword) + len(tab_movie_link) + len(tab_name) + len(tab_person_info) + len(tab_role_type) + len(tab_title)

print(numberOfQueries)

def insert_query(table, tab):
    query = "INSERT INTO " + table + " VALUES "
    if len(tab) > 0:
        query+= tab[0]
        for row in tab[1:]:
            query+= ",\n"
            query+= row
    return query + ";"

var = insert_query("title (id, title, imdb_index, kind_id, production_year, imdb_id, phonetic_code, episode_of_id, season_nr, episode_nr, series_years, md5sum)", tab_title)

print(var)