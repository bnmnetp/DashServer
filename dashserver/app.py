# Run this app with `python app.py` and
# visit http://127.0.0.1:8050/ in your web browser.
# See - https://dash.plotly.com/layout for the docs getting started
# Most of what we want to do will probably involve "long callbacks" https://dash.plotly.com/long-callbacks
# this will avoid http timeouts

import dash
from dash import Dash, html, dcc
from dash.long_callback import DiskcacheLongCallbackManager
from dash.dependencies import Input, Output
import diskcache
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from sqlalchemy import create_engine

cache = diskcache.Cache("./cache")
long_callback_manager = DiskcacheLongCallbackManager(cache)

app = Dash(__name__)

# eng = create_engine("postgresql://bmiller:@localhost:8541/runestone_archive")

COURSE = "Win21-SI206"
CHAPTER = "functions"
BASE = "py4e-int"

colors = {"background": "#111111", "text": "#7FDBFF"}


def get_chapters():
    eng = create_engine("postgresql://bmiller:@runestoneM1.local/runestone_archive")

    chap_data = pd.read_sql_query
    res = pd.read_sql_query(
        f"""
    select chapter_name as label, chapter_label as value from chapters
    where course_id = '{BASE}' and chapter_num < 999
    order by chapter_num
    """,
        eng,
    )

    return res.to_dict(orient="records")


@dash.callback(
    output=Output("chapter-progress-graph", "figure"),
    inputs=Input("chapter_list", "value"),
    background=True,
    manager=long_callback_manager,
)
def do_callback(chap_label):
    return make_progress_graph(chap_label)


def make_progress_graph(chapter):
    eng = create_engine("postgresql://bmiller:@runestoneM1.local/runestone_archive")

    progress = pd.read_sql_query(
        f"""select sub_chapter_id, status, count(*)
    from user_sub_chapter_progress where course_name = '{COURSE}' and chapter_id = '{chapter}'
    group by sub_chapter_id, status
    order by sub_chapter_id""",
        eng,
    )
    scdf = progress.groupby("sub_chapter_id").agg(total=("count", "sum"))
    pdf = progress.groupby(["sub_chapter_id", "status"]).agg(
        students=("count", "sum"), ccount=("count", "min")
    )
    pdf = pdf.reset_index()
    pdf["pct"] = pdf.apply(
        lambda row: row.students / scdf.loc[row.sub_chapter_id], axis=1
    )
    smap = {-1: "Not Started", 0: "Started", 1: "Complete"}
    pdf["named_status"] = pdf.status.map(lambda x: smap[x])

    # assume you have a "long-form" data frame
    # see https://plotly.com/python/px-arguments/ for more options

    fig = px.bar(
        pdf, x="pct", y="sub_chapter_id", color="named_status", width=700, height=1000
    )

    fig.update_layout(
        plot_bgcolor=colors["background"],
        paper_bgcolor=colors["background"],
        font_color=colors["text"],
    )
    return fig


@dash.callback(
    output=Output("student-progress-graph", "figure"),
    inputs=Input("chapter_list", "value"),
    background=True,
    manager=long_callback_manager,
)
def do_callback(chap_label):
    return make_student_activity_graph(chap_label)


def make_student_activity_graph(chap):
    eng = create_engine("postgresql://bmiller:@runestoneM1.local/runestone_archive")

    sa = pd.read_sql_query(
        f"""
    select sid, Etype, count(*) from (
    select sid,
      case
        when event = 'page' then 'Page View'
        when event = 'activecode' then 'Run Program'
        else 'Other'
      end as EType
    from useinfo where course_id = '{COURSE}' ) as T
    group by sid, EType
    order by sid
    """,
        eng,
    )
    sa = sa[sa.sid.str.contains("@") == False]
    fig = px.bar(sa, x="count", y="sid", color="etype", width=700, height=1200)

    return fig


app.layout = html.Div(
    [
        html.H1(
            children="Student Progress",
            style={"textAlign": "center", "color": colors["text"]},
        ),
        dcc.Dropdown(
            id="chapter_list",
            options=get_chapters(),
            value="intro",
        ),
        html.Div(
            children=[
                """Chapter Progress""",
                dcc.Graph(id="chapter-progress-graph"),
            ]
        ),
        html.Div(
            children=["""Student Progress""", dcc.Graph(id="student-progress-graph")]
        ),
    ]
)

if __name__ == "__main__":
    app.run_server(debug=True)
