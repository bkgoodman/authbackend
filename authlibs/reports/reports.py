# vim:shiftwidth=2:expandtab
import pprint
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from ..db_models import Member, db, Resource, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, Logs, ApiKey, Blacklist
from functools import wraps
import json
import subprocess
import os
import inspect
from google import genai
#from .. import requireauth as requireauth
from .. import utilities as authutil
from ..utilities import _safestr as safestr
from authlibs import eventtypes
from authlibs import payments as pay
from sqlalchemy import case, DateTime, text, inspect as sql_inspect

import logging
from authlibs.init import GLOBAL_LOGGER_LEVEL
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("reports", __name__, template_folder='templates', static_folder="static",url_prefix="/reports")

# ------------------------------------------------------------
# Reporting controllers
# ------------------------------------------------------------

@blueprint.route('/oldreports', methods=['GET'])
@roles_required(['Admin','Finance'])
@login_required
def oldreports():
    """(Controller) Display some pre-defined report options"""
    stats = {} #getDataDiscrepancies()
    return render_template('oldreports.html',stats=stats)

@blueprint.route('/', methods=['GET'])
@roles_required(['Admin','Finance'])
@login_required
def reports():
    """(Controller) Display some pre-defined report options"""
    return render_template('reports.html')

@blueprint.route('/bigbrain', methods=['GET'])
@roles_required(['Admin','Finance'])
@login_required
def bigbrain_page():
    """(Controller) Display BigBrain AI query interface"""
    return render_template('ai_query.html')

@blueprint.route('/bigbrain', methods=['POST'])
@roles_required(['Admin','Finance'])
@login_required
def bigbrain():
    """(Controller) Process BigBrain AI database query"""
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        
        if not question:
            return json.dumps({'status': 'error', 'message': 'Question is required'})
        
        # Initialize Google AI client
        api_key = current_app.config['globalConfig'].Config.get('GoogleAI', 'token', fallback='')
        
        if not api_key:
            return json.dumps({'status': 'error', 'message': 'Google AI API key not configured in config'})
        
        client = genai.Client(api_key=api_key)
        
        # Get database schema using SQLAlchemy
        schema = get_database_schema()
        
        # Generate SQL query
        sql = generate_sql_query(client, schema, question)
        
        # Execute SQL query
        result = execute_sql_query(sql)
        
        # Generate final report
        answer = generate_final_report(client, result, question)
        
        return json.dumps({
            'status': 'ok',
            'sql': sql,
            'answer': answer
        })
        
    except Exception as e:
        logger.error(f"AI query error: {e}")
        return json.dumps({'status': 'error', 'message': str(e)})

def get_database_schema():
    """Get database schema using SQLAlchemy inspection"""
    schema_parts = []
    
    # Get main database schema
    inspector = sql_inspect(db.engine)
    
    schema_parts.append("First database called makeit.db:")
    table_names = inspector.get_table_names()
    schema_parts.append(f"\nAvailable tables: {', '.join(table_names)}")
    
    for table_name in table_names:
        columns = inspector.get_columns(table_name)
        schema_parts.append(f"\nTable: {table_name}")
        for col in columns:
            schema_parts.append(f"  {col['name']} {col['type']}")
    
    # Get tools and resources mapping if tables exist
    tools = []
    resources = []
    
    if 'tools' in table_names:
        try:
            tools = db.session.execute(text("SELECT id, name FROM tools")).fetchall()
        except Exception as e:
            logger.warning(f"Could not query tools table: {e}")
    
    if 'resources' in table_names:
        try:
            resources = db.session.execute(text("SELECT id, name FROM resources")).fetchall()
        except Exception as e:
            logger.warning(f"Could not query resources table: {e}")
    
    if tools:
        schema_parts.append("\n\ntools defined as:")
        for tool_id, tool_name in tools:
            schema_parts.append(f"  {tool_id}: {tool_name}")
    
    if resources:
        schema_parts.append("\n\nresources defined as:")
        for res_id, res_name in resources:
            schema_parts.append(f"  {res_id}: {res_name}")
    
    schema_parts.append("""
    
Take SPECIAL care when writing SQL queries, that any tables you reference above must be specified with a "makeit." prefix.
""")
    
    return "\n".join(schema_parts)

def generate_sql_query(client, schema, question):
    """Generate SQL query using Google AI"""
    system = """
You are an automated database agent - return sqlite3 SQL only. 
Do not do anything to drop, modify add database at all. Never return more than 250 entries. Return error if trying to modify databases
Be sure to include:

Make sure each table reference uses the correct attached database!
return ONLY raw SQL - no block around it

You are ONLY to determine what SQL query you would need to execute to give yourself the data required to answer the user's question.
"""
    
    response = client.models.generate_content(
        model="gemini-3-pro-preview",
        config=genai.types.GenerateContentConfig(
            system_instruction=system),
        contents=f"{schema}\n\nThe user's question is as follows: {question}",
    )
    
    return response.text.strip()

def execute_sql_query(sql):
    """Execute SQL query using SQLAlchemy"""
    try:
        # Split SQL into individual statements
        statements = []
        current_statement = ""
        
        for line in sql.split('\n'):
            line = line.strip()
            if not line or line.startswith('--'):
                continue
            current_statement += line + '\n'
            if line.endswith(';'):
                statements.append(current_statement.strip())
                current_statement = ""
        
        if current_statement.strip():
            statements.append(current_statement.strip())
        
        # Execute each statement and collect results
        all_results = []
        
        for i, statement in enumerate(statements):
            if not statement.strip():
                continue
                
            try:
                result = db.session.execute(text(statement))
                
                # Format the result as text
                if result.returns_rows:
                    rows = result.fetchall()
                    if rows:
                        # Get column names
                        columns = result.keys()
                        
                        # Format as table
                        output = []
                        if i > 0:  # Add separator for multiple queries
                            output.append(f"\n--- Query {i+1} Results ---")
                        output.append("\t".join(str(col) for col in columns))
                        for row in rows:
                            output.append("\t".join(str(val) if val is not None else 'NULL' for val in row))
                        all_results.extend(output)
                    else:
                        if i == 0:  # Only show "No results" for first query
                            all_results.append("No results returned")
                else:
                    if i == 0:  # Only show success message for first query
                        all_results.append(f"Query executed successfully. Rows affected: {result.rowcount}")
                    else:
                        all_results.append(f"Query {i+1} executed successfully. Rows affected: {result.rowcount}")
                        
            except Exception as e:
                logger.error(f"SQL execution error for statement {i+1}: {e}\nStatement: {statement}")
                if i == 0:  # Return error for first statement
                    return f"SQL Error: {str(e)}"
                else:
                    all_results.append(f"Error in query {i+1}: {str(e)}")
        
        return "\n".join(all_results) if all_results else "No valid SQL statements found"
            
    except Exception as e:
        logger.error(f"SQL execution error: {e}\nSQL: {sql}")
        return f"SQL Error: {str(e)}"

def generate_final_report(client, result, question):
    """Generate final HTML report using Google AI"""
    system = """
user has asked a question, and then you queried a bunch of data to help answer the question or generate the report that the user asked. Use the attached data to help best answer question or generate report for the user. Provide full answer in HTML format
"""
    
    response = client.models.generate_content(
        model="gemini-3-pro-preview",
        config=genai.types.GenerateContentConfig(
            system_instruction=system),
        contents=f"{result}\n\nThe user's question is as follows: {question}",
    )
    
    return response.text.strip()


# Not used right now - I think it is exclusivley old "pinpayments" stuff??
def getDataDiscrepancies():
    """Extract some commonly used statistics about data not matching"""
    # Note" SQLLIte does not support full outer joins, so we have some duplication of effort...
    stats = {}
    sqlstr = """select m.member,m.active,m.plan,p.expires_date,p.updated_date from members m
            left outer join payments p on p.member=m.member where p.member is null order by m.member"""
    stats['members_nopayments'] = db.session.execute(sqlstr)
    sqlstr = """select p.member,p.email,a.member from payments p left outer join accessbymember a
            on p.member=a.member where a.member is null and p.expires_date > Datetime('now') order by p.member"""
    stats['paid_noaccess'] = query_db(sqlstr)
    sqlstr = """select p.member,m.member from payments p left outer join members m on p.member=m.member
        where m.member is null"""
    stats['payments_nomembers'] = query_db(sqlstr)
    sqlstr = """select a.member from accessbymember a left outer join members m on a.member=m.member
            where m.member is null and a.member is not null group by a.member"""
    stats['access_nomembers'] = query_db(sqlstr)
    sqlstr = """select distinct(resource) as resource from accessbymember where resource not in (select name from resources)"""
    stats['access_noresource'] = query_db(sqlstr)
    sqlstr = "select DISTINCT(member) from tags_by_member where member not in (select member from members) order by member"
    stats['tags_nomembers'] = query_db(sqlstr)
    sqlstr = """select DISTINCT(a.member), p.expires_date from accessbymember a join payments p on a.member=p.member where
            p.expires_date < Datetime('now')"""
    stats['access_expired'] = query_db(sqlstr)
    sqlstr = """select member,expires_date from payments where expires_date > Datetime('now','-60 days')
                and expires_date < Datetime('now')"""
    stats['recently_expired'] = query_db(sqlstr)
    sqlstr = "select member,expires_date,customerid,count(*) from payments group by member having count(*) > 1"
    stats['duplicate_payments'] = query_db(sqlstr)
    return stats

# ------------------------------------------------------------
# Blacklist entries
# - Ignore bad pinpayments records, mainly
# ------------------------------------------------------------

@blueprint.route('/blacklist', methods=['GET'])
@login_required
@roles_required(['Admin','Finance'])
def blacklist():
    """(Controller) Show all the Blacklist entries"""
    #    sqlstr = "select entry,entrytype,reason,updated_date from blacklist"
    #blacklist = db.session.execute(sqlstr)
    blacklist = Blacklist.query.all()
    return render_template('blacklist.html',blacklist=blacklist)

@blueprint.route('/runreport/<string:report>', methods=['GET'])
@login_required
@roles_required(['Admin','Finance'])
def runreport(report):
    report = report.replace("/","")
    report = report.replace(".","")
    try:
        res = {
                "status": "ok",
                "text":f"This is a run of report {report}"
                }
        f = subprocess.Popen(["./"+report+".py"],cwd="authlibs/reports/reports/",stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        txt = f.stdout.read().decode("utf-8")
        txt += f.stderr.read().decode("utf-8")
        result = f.wait()
        res['text']=txt + f"Result: {result}"
    except BaseException as e:
        res = {
                "status": "error",
                "text":f"BaseException {e}"
                }
    return (json.dumps(res,indent=2), 200, {'Content-type': 'application/json', 'Content-Language': 'en'})


def register_pages(app):
	app.register_blueprint(blueprint)
