import numpy as np
import math
import json
import pandas as pd
import matplotlib.pyplot as plt
from PrayTimes import prayTimes
import requests
from bs4 import BeautifulSoup
import math
from ddgs import DDGS
import re
import plotly.graph_objects as go
from datetime import datetime
from timezonefinder import TimezoneFinder
import pytz


def get_flight_history(flight_number, sel_index=0):
    url = "https://www.flightaware.com/live/flight/" + flight_number + "/history"
    hist_link = []
    # Define headers to mimic a browser request
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors
        soup = BeautifulSoup(response.text, "html.parser")
        # Find the link with the specific pattern
        for link in soup.find_all("a"):
            href = link.get("href")
            if href and "/history/2" in href:
                hist_link = hist_link + ["https://www.flightaware.com" + href]

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    }
    url = hist_link[sel_index] + "/tracklog"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()  # Raise error on bad response

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find_all("table")
    df = pd.read_html(str(table))
    return df


def Parse24HrTime(time_24hr):
    invalidTime = "-----"
    if time_24hr == invalidTime:
        return np.nan, np.nan
    if time_24hr[0] == "-":
        hr = 0
        mins = 0
    else:
        hr = int(time_24hr.split(":")[0])
        mins = int(time_24hr.split(":")[1])

    return (hr, mins)


def Extract24HrTime(time_12hr):
    invalidTime = "-----"
    if time_12hr == invalidTime:
        return np.nan, np.nan
    else:
        exc_day = time_12hr[-2:]
        exc_time = time_12hr[:-3]
        hr = int(exc_time.split(":")[0])
        mins = int(exc_time.split(":")[1])

        if exc_day == "PM":
            if hr != 12:
                hr += 12
        else:
            if hr == 12:
                hr = 0

        return (hr, mins)


def ConvertTo12Hr(time_24):
    mins = (time_24 - int(time_24)) * 60
    hrs = int(time_24)
    if hrs > 12:
        day = "PM"
        hrs -= 12
    elif hrs == 12:
        day = "PM"
        hrs = hrs
    elif hrs == 0:
        day = "AM"
        hrs += 12
    else:
        day = "AM"
    return (hrs, int(mins), day)


def calculate_inflight_prayertime(diff_time, flight_times):
    diff_indices = np.argwhere(diff_time <= 0.2)
    if len(diff_indices) == 0:
        return np.nan, np.nan
    else:
        # prayertime = ConvertTo12Hr(flight_times[diff_indices[0,0]])
        prayertime = flight_times[diff_indices[0, 0]]
        return diff_indices[0], prayertime


def get_repeated_substring(s):
    for i in range(1, len(s) // 2 + 1):
        part = s[:i]
        if s == part * (len(s) // len(part)):
            return part
    return s  # return original if no clean repetition found


def qibla_direction(lat, lon):
    # Convert degrees to radians
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.radians(21.4225)  # Kaaba
    lon2 = math.radians(39.8262)  # Kaaba

    delta_lon = lon2 - lon1

    x = math.sin(delta_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(
        delta_lon
    )

    theta = math.atan2(x, y)
    bearing = (math.degrees(theta) + 360) % 360

    return bearing  # in degrees


def duckduckgo_link(flightnumber, query):
    fa_string = "flightaware.com"
    numbers_flightnumber = re.findall(r"\d+", flightnumber)[0]
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=100)
        for r in results:
            hlink = r["href"]

            if (fa_string in hlink) and (numbers_flightnumber in hlink):
                return r["href"]
    return None


def get_tz_offset_loc(date, coordinates, eastern=True):
    if eastern:
        tz = pytz.timezone("US/Eastern")
    else:
        tf = TimezoneFinder()
        timezone_str = tf.timezone_at(lat=coordinates[0], lng=coordinates[1])
        tz = pytz.timezone(timezone_str)
    localized_dt = tz.localize(date)
    utc_offset_hours = localized_dt.utcoffset().total_seconds() / 3600
    return utc_offset_hours


def find_tz_offset(calc_date, calc_coordinates, origin_coordinates, eastern=True):
    # calc_coordinates: [lat ,long]
    # orig_coordinates: [lat ,long]

    date = datetime(calc_date[0], calc_date[1], calc_date[2])

    utc_offset_calc = get_tz_offset_loc(date, calc_coordinates, eastern)
    utc_offset_origin = get_tz_offset_loc(date, origin_coordinates, eastern=False)
    return (utc_offset_origin - utc_offset_calc, utc_offset_origin)


def timezone_correction(t_hr, t_min, correction_offset):
    hr_correction = int(correction_offset)
    min_correction = (correction_offset - int(correction_offset)) * 60
    return t_hr - hr_correction, int(t_min - min_correction)


def rotate_shape(x, y, angle_rad):
    """Rotate shape (x, y) around origin (0, 0)."""
    x_rot = []
    y_rot = []
    for xi, yi in zip(x, y):
        x_rot.append(xi * np.cos(angle_rad) - yi * np.sin(angle_rad))
        y_rot.append(xi * np.sin(angle_rad) + yi * np.cos(angle_rad))
    return x_rot, y_rot


def draw_plane_with_arrow(
    relative_angle_deg, title="", plane_heading_deg=0, arrow_length=2
):
    # Plane outline (top-down, wireframe, pointing up)
    plane_x = [
        0,
        0.2,
        0.2,
        0.6,
        0.6,
        0.2,
        0.2,
        0.5,
        0.5,
        0.2,
        0.2,
        -0.2,
        -0.2,
        -0.5,
        -0.5,
        -0.2,
        -0.2,
        -0.6,
        -0.6,
        -0.2,
        -0.2,
        0,
    ]
    plane_y = [
        1,
        0.6,
        0.3,
        0.2,
        -0.2,
        -0.3,
        -0.6,
        -0.6,
        -0.8,
        -0.8,
        -0.6,
        -0.6,
        -0.8,
        -0.8,
        -0.6,
        -0.6,
        -0.3,
        -0.2,
        0.2,
        0.3,
        0.6,
        1,
    ]

    # Rotate plane outline by heading
    heading_rad = np.radians(plane_heading_deg)
    plane_x_rot, plane_y_rot = rotate_shape(plane_x, plane_y, heading_rad)

    # Total arrow angle in global frame (0° = up)
    total_angle_rad = np.radians(plane_heading_deg + relative_angle_deg)
    arrow_dx = arrow_length * np.sin(total_angle_rad)
    arrow_dy = arrow_length * np.cos(total_angle_rad)

    # Arrow start (nose of plane) and end
    x_start, y_start = 0, 0
    x_end = x_start + arrow_dx
    y_end = y_start + arrow_dy

    fig = go.Figure()

    # Plane wireframe
    fig.add_trace(
        go.Scatter(
            x=plane_x_rot,
            y=plane_y_rot,
            mode="lines",
            line=dict(color="black", width=2),
            name="Plane Outline",
        )
    )

    # Arrow
    fig.add_annotation(
        x=x_end,
        y=y_end,
        ax=x_start,
        ay=y_start,
        xref="x",
        yref="y",
        axref="x",
        ayref="y",
        showarrow=True,
        arrowhead=3,
        arrowsize=1.5,
        arrowwidth=2,
        arrowcolor="red",
    )

    # Angle label near the arrow tip
    label_offset = 0.2
    fig.add_trace(
        go.Scatter(
            x=[x_end + label_offset],
            y=[y_end + label_offset],
            mode="text",
            text=[f"{int(relative_angle_deg)}°"],
            textposition="top center",
            textfont=dict(size=14, color="red"),
            showlegend=False,
        )
    )

    fig.update_layout(
        title=title,
        xaxis=dict(scaleanchor="y", scaleratio=1, visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
        width=600,
        height=600,
    )

    return fig


def salah_calculator(
    flightnumber,
    departure_time,
    prayer_method,
    date=(2025, 8, 1),
    flight_early=False,
    debug=False,
    datalog_index=0,
):
    # Search flightawre's flightnumber
    dg_search_string = flightnumber + " flightaware.com "
    fa_string = duckduckgo_link(flightnumber, dg_search_string)
    fa_flightnumber = fa_string.split("/")[-1]

    # Get flight log history
    pd_flighthistory = get_flight_history(fa_flightnumber, sel_index=datalog_index)
    df = pd_flighthistory[0]  # Constructs a pandas dataframe with the pulled
    # Flight history

    df.to_csv("flightdata_raw.csv")
    # cleanup: Removing the stray rows with reporting facility names
    unique_facilities = df["Reporting Facility"].unique()
    unique_facilities = unique_facilities[1:]
    for unique_facility in unique_facilities:
        df = df[~df["LatitudeLat"].str.contains(unique_facility[:5])]
    df = df[~df["LatitudeLat"].str.contains("Gap")]  # removes any gaps in the data

    df = df.iloc[5:-15]  # Ignoring the first and last 5 rows

    df.to_csv("flightdata_cleaned.csv")

    print("Flight data extracted!")

    prayTimes.setMethod(
        prayer_method
    )  # paramaterS: MWL, ISNA, Egypt, Makkah, Karachi, Tehran, Jafari
    format = "%I:%M %p"
    calc_coordinates = [43.65, -79.34]
    # UTC offset for prayer time calculation
    tz = pytz.timezone("US/Eastern")
    localized_dt = tz.localize(datetime(date[0], date[1], date[2]))
    utc_offset_hours = localized_dt.utcoffset().total_seconds() / 3600

    # Time conversion between flightaware and origin:
    orig_latitude = float(df.LatitudeLat.iloc[0][:6])
    orig_longitude = float(df.LongitudeLon.iloc[0][:6])
    origin_coordinates = [orig_latitude, orig_longitude]
    correction_offset, origin_utc = find_tz_offset(
        date, calc_coordinates, origin_coordinates, eastern=True
    )

    # Adjust for delayed/early flight:

    route_start_time = df.iloc[0]["Time (EDT)EDT"][4:]
    # Convert route_start_time to source time

    ext_hr_flight_uncorrected, ext_mins_flight_uncorrected = Extract24HrTime(
        route_start_time
    )
    ext_hr_flight, ext_mins_flight = timezone_correction(
        ext_hr_flight_uncorrected, ext_mins_flight_uncorrected, correction_offset
    )

    route_start_time = ext_hr_flight + ext_mins_flight / 60

    ext_hr_flight, ext_mins_flight = Extract24HrTime(departure_time)

    departure_time = ext_hr_flight + ext_mins_flight / 60
    if flight_early:
        if route_start_time < departure_time:
            route_start_time += 24
        time_correction = departure_time - route_start_time
    else:
        if departure_time < route_start_time:
            departure_time += 24
    time_correction = departure_time - route_start_time

    # Go through rows of flight data, and calculate prayer times at each coordinate

    NumRecords = len(df)

    longitudes = np.zeros(NumRecords)
    latitudes = np.zeros(NumRecords)
    fajr_times = np.zeros(NumRecords)
    dhuhr_times = np.zeros(NumRecords)
    asr_times = np.zeros(NumRecords)
    isha_times = np.zeros(NumRecords)
    maghrib_times = np.zeros(NumRecords)
    sunrise_times = np.zeros(NumRecords)
    altitudes = np.zeros(NumRecords)
    headings = np.zeros(NumRecords)

    flight_times = np.zeros(NumRecords)
    invalidTime = "-----"
    prev_height = 0
    ind = 0
    for ind_rec, row in df.iterrows():
        headings[ind] = df["CourseDir"][ind_rec][2:-1]
        height = float(get_repeated_substring(str(df.feet[ind_rec])))

        if np.isnan(height):
            height = prev_height
        else:
            prev_height = height

        altitudes[ind] = height
        loc_latitude = float(df.LatitudeLat[ind_rec][:6])
        loc_longitude = float(df.LongitudeLon[ind_rec][:6])
        coordinates = (loc_latitude, loc_longitude, height * 0.3048)
        prayer_times = prayTimes.getTimes(date, coordinates, origin_utc)

        fajr_time = prayer_times["fajr"]
        dhuhr_time = prayer_times["dhuhr"]
        asr_time = prayer_times["asr"]
        maghrib_time = prayer_times["maghrib"]
        isha_time = prayer_times["isha"]
        sunrise_time = prayer_times["sunrise"]

        # Convert 12hr flight time to 2hrs and mins
        ext_hr_flight_uncorrected, ext_mins_flight_uncorrected = Extract24HrTime(
            df["Time (EDT)EDT"][ind_rec][4:]
        )

        ext_hr_flight, ext_mins_flight = timezone_correction(
            ext_hr_flight_uncorrected, ext_mins_flight_uncorrected, correction_offset
        )

        # Parses 24hr time into hrs and minutes
        ext_hr_fajr, ext_mins_fajr = Parse24HrTime(fajr_time)
        ext_hr_dhuhr, ext_mins_dhuhr = Parse24HrTime(dhuhr_time)
        ext_hr_asr, ext_mins_asr = Parse24HrTime(asr_time)
        ext_hr_maghrib, ext_mins_maghrib = Parse24HrTime(maghrib_time)
        ext_hr_isha, ext_mins_isha = Parse24HrTime(isha_time)
        ext_hr_sunrise, ext_mins_sunrise = Parse24HrTime(sunrise_time)

        # Converts all times into just hours:
        flight_times[ind] = np.mod(
            ext_hr_flight + ext_mins_flight / 60 + time_correction, 24
        )
        fajr_times[ind] = ext_hr_fajr + ext_mins_fajr / 60
        sunrise_times[ind] = ext_hr_sunrise + ext_mins_sunrise / 60
        dhuhr_times[ind] = ext_hr_dhuhr + ext_mins_dhuhr / 60
        asr_times[ind] = ext_hr_asr + ext_mins_asr / 60
        maghrib_times[ind] = ext_hr_maghrib + ext_mins_maghrib / 60
        isha_times[ind] = ext_hr_isha + ext_mins_isha / 60
        longitudes[ind] = loc_longitude
        latitudes[ind] = loc_latitude
        ind += 1

    # Find prayer times, and the qibla directions:
    diff_dhuhr = np.abs(dhuhr_times - flight_times)
    diff_asr = np.abs(asr_times - flight_times)
    diff_maghrib = np.abs(maghrib_times - flight_times)
    diff_isha = np.abs(isha_times - flight_times)
    diff_fajr = np.abs(fajr_times - flight_times)
    diff_sunrise = np.abs(sunrise_times - flight_times)

    fajr_ind, fajr_time = calculate_inflight_prayertime(diff_fajr, flight_times)
    sunrise_ind, sunrise_time = calculate_inflight_prayertime(
        diff_sunrise, flight_times
    )
    dhuhr_ind, dhuhr_time = calculate_inflight_prayertime(diff_dhuhr, flight_times)
    asr_ind, asr_time = calculate_inflight_prayertime(diff_asr, flight_times)
    maghrib_ind, maghrib_time = calculate_inflight_prayertime(
        diff_maghrib, flight_times
    )
    isha_ind, isha_time = calculate_inflight_prayertime(diff_isha, flight_times)

    prayer_labels = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
    prayer_indices = [fajr_ind, sunrise_ind, dhuhr_ind, asr_ind, maghrib_ind, isha_ind]
    prayer_times_list = [
        fajr_time,
        sunrise_time,
        dhuhr_time,
        asr_time,
        maghrib_time,
        isha_time,
    ]

    combined = []
    for idx_obj, t, label in zip(prayer_indices, prayer_times_list, prayer_labels):
        if (
            isinstance(idx_obj, np.ndarray)
            and idx_obj.size > 0
            and not np.isnan(idx_obj[0])
        ):
            idx_int = int(idx_obj[0])  # first occurrence
            t_val = float(t) if not (isinstance(t, float) and np.isnan(t)) else None
        else:
            idx_int = None
            t_val = None
        combined.append((idx_int, t_val, label))

    # Sort by index, None at the end
    combined.sort(key=lambda x: (x[0] is None, x[0] if x[0] is not None else 10**9))
    sorted_indices, sorted_times, sorted_labels = (
        zip(*combined) if combined else ([], [], [])
    )

    # Compute absolute/relative qiblah headings only for valid indices
    qibla_abs = []
    headings_abs = []
    for idx in sorted_indices:
        if idx is not None:
            # NOTE: your code had a small indexing bug here
            # longitudes/latitudes are 1D arrays, so use [idx] not [loc_ind[0]] / [loc_ind]
            q_dir = qibla_direction(latitudes[idx], longitudes[idx])
            qibla_abs.append(q_dir)
            headings_abs.append(float(headings[idx]))
        else:
            qibla_abs.append(None)
            headings_abs.append(None)

    qibla_rel = []
    for q, h in zip(qibla_abs, headings_abs):
        qibla_rel.append(None if (q is None or h is None) else (q - h))

    # Build schedule and figures
    def to_12h(t):
        if t is None:
            return "—"
        hr, m, ap = ConvertTo12Hr(t)
        return f"{hr:02d}:{m:02d} {ap}"

    schedule = []
    for idx, t, label in zip(sorted_indices, sorted_times, sorted_labels):
        schedule.append(
            {
                "label": label,
                "index": idx if idx is not None else "—",
                "time_24h": None if t is None else round(t, 3),
                "time_12h": to_12h(t),
            }
        )

    # Qiblah figs
    qibla_figs = []
    for rel, label in zip(qibla_rel, sorted_labels):
        if rel is not None:
            fig = draw_plane_with_arrow(
                relative_angle_deg=rel, title=f"Qiblah for: {label}", arrow_length=1
            )
            qibla_figs.append(fig)

    # Optional debug figure (matplotlib)
    debug_fig = None
    if debug:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(7, figsize=(10, 10))
        ax[0].plot(flight_times)
        ax[0].plot(fajr_times)
        ax[0].legend(["flight", "Fajr"])
        ax[1].plot(flight_times)
        ax[1].plot(sunrise_times)
        ax[1].legend(["flight", "Sunrise"])
        ax[2].plot(flight_times)
        ax[2].plot(dhuhr_times)
        ax[2].legend(["flight", "Dhuhr"])
        ax[3].plot(flight_times)
        ax[3].plot(asr_times)
        ax[3].legend(["flight", "Asr"])
        ax[4].plot(flight_times)
        ax[4].plot(maghrib_times)
        ax[4].legend(["flight", "Maghrib"])
        ax[5].plot(flight_times)
        ax[5].plot(isha_times)
        ax[5].legend(["flight", "Isha"])
        ax[6].plot(altitudes)
        ax[6].set_ylabel("altitude (ft)")
        debug_fig = fig

    return {"schedule": schedule, "qibla_figs": qibla_figs, "debug_fig": debug_fig}
