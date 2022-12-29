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
import pandas as pd
from sqlalchemy import create_engine
import dash_bootstrap_components as dbc

cache = diskcache.Cache("./cache")
long_callback_manager = DiskcacheLongCallbackManager(cache)

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])


COURSE = "Win21-SI206"
CHAPTER = "functions"
BASE = "py4e-int"

colors = {"background": "#111111", "text": "#7FDBFF"}

# DBURL_CABIN = "postgresql://bmiller:@runestoneM1.local/runestone_archive"
DBURL = "postgresql://bmiller:@localhost:8541/runestone_archive"


def get_chapters():
    # since the various chart creating things are asynchronous each needs their own engine.
    # There must be a better way than creating and disposing of an engine.  But I'll need
    # to do more research
    eng = create_engine(DBURL)

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


#
# Chapter / SubChapter progress
#


@dash.callback(
    output=Output("chapter-progress-graph", "figure"),
    inputs=Input("chapter_list", "value"),
    background=True,
    manager=long_callback_manager,
)
def do_callback(chap_label):
    return make_progress_graph(chap_label)


def make_progress_graph(chapter):
    eng = create_engine(DBURL)

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


#
# Student Activity Summary
#
# This callback takes a bit of getting used to
# `output` contains the id of a thing in the page layout that will be replaced as a result of the
# callback. It is a figure.
# The `input` Hooks this up to one or more input elements.  For example a dropdown or button,
# For traditional html input methods you would typically want the value but some elements created by
# Dash have special values such as n_clicks for a button.
# the manager is typically a celery/redis thing in production but for development it is easy to use diskcache.
#
@dash.callback(
    output=Output("student-progress-graph", "figure"),
    inputs=Input("chapter_list", "value"),
    background=True,
    manager=long_callback_manager,
)
def do_callback(chap_label):
    return make_student_activity_graph(chap_label)


def make_student_activity_graph(chap):
    eng = create_engine(DBURL)

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


#
# Donut Charts by subchapter
#
@app.callback(Output("subchapter_list", "options"), Input("chapter_list", "value"))
def set_cities_options(selected_chapter):
    # select all subchapters for the given chapter in the BASECOURSE
    res = pd.read_sql_query(
        f"""
    select sub_chapter_name as label, sub_chapter_label as value
        from sub_chapters join chapters on chapter_id = chapters.id
        where chapters.course_id = 'py4e-int'
            and chapters.chapter_label = '{selected_chapter}'
            and sub_chapter_num != 999
        order by sub_chapter_num""",
        DBURL,
    )

    return res.to_dict(orient="records")


# Now we need another callbackk that uses the output of the selected chapter and
# subchapter so that we can generate the donut charts.
@app.callback(
    Output("bag_of_donuts", "figure"),
    Input("chapter_list", "value"),
    Input("subchapter_list", "value"),
)
def make_the_donuts(chapter, subchapter):
    pass


# This layout describes the page.  There is no html and no template, just this.
# Under the hood Dash generates the required html/css/javascript using React.
#
app.layout = html.Div(
    children=[
        html.Div(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            children=[
                                html.H1(
                                    children="Student Progress",
                                    style={
                                        "textAlign": "center",
                                        "color": colors["text"],
                                    },
                                ),
                                """Chapter Progress""",
                                dcc.Dropdown(
                                    id="chapter_list",
                                    options=get_chapters(),
                                    value="intro",
                                ),
                                dcc.Graph(id="chapter-progress-graph"),
                            ],
                            style={"width": "48%"},
                        ),
                        dbc.Col(
                            children=[
                                """Student Progress""",
                                dcc.Graph(id="student-progress-graph"),
                            ],
                            style={"width": "48%"},
                        ),
                    ]
                ),
                # Here begins the donut chart section...
                # This adds a bunch of complexity now because we want the chapter dropdown to cause
                # this dropdown to update with its subchapters as well as updating the chapter information
                # in previous outputs.  See `Dash App With Chained Callbacks <https://dash.plotly.com/basic-callbacks>`_ for a good example
                dbc.Row(
                    [
                        dcc.Dropdown(
                            id="subchapter_list",
                        ),
                        dcc.Graph(id="bag_of_donuts"),
                    ]
                ),
            ]
        )
    ],
)

if __name__ == "__main__":
    app.run_server(debug=True)
