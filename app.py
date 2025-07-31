import os
from flask import Flask, render_template, request, jsonify
import requests
import datetime
from datetime import timedelta, timezone # Import timezone

app = Flask(__name__)

# --- YOUR API KEYS ARE DIRECTLY EMBEDDED HERE ---
# These values will be used directly by the application.
OPENWEATHERMAP_API_KEY = '2506d5feb64078d452cc0c138bce3401'
GEMINI_API_KEY = 'AIzaSyB38nLeRLgmALs9Bu6A4MoEdUqq3X1Clz8'
# -------------------------------------------------

@app.route('/')
def index():
    """
    Renders the main index.html page for the weather application.
    """
    return render_template('index.html')

@app.route('/weather', methods=['GET'])
def get_weather():
    """
    Fetches current weather and 5-day/3-hour forecast data for a given city
    using the OpenWeatherMap API.
    """
    city = request.args.get('city')
    if not city:
        return jsonify({"error": "City parameter is missing"}), 400

    # OpenWeatherMap API endpoint for current weather
    current_weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHERMAP_API_KEY}&units=metric"
    # OpenWeatherMap API endpoint for 5-day / 3-hour forecast
    forecast_url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OPENWEATHERMAP_API_KEY}&units=metric"

    try:
        # Fetch current weather
        current_response = requests.get(current_weather_url)
        current_response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        current_weather_data = current_response.json()

        if str(current_weather_data.get('cod')) == '404':
            return jsonify({"error": "City not found"}), 404
        elif str(current_weather_data.get('cod')) != '200':
            # Handle other OpenWeatherMap API errors
            return jsonify({"error": current_weather_data.get('message', 'Unknown OpenWeatherMap API error')}), current_weather_data.get('cod', 500)

        # Extract relevant current weather information
        main_weather = current_weather_data['main']
        weather_description = current_weather_data['weather'][0]['description']
        weather_icon = current_weather_data['weather'][0]['icon']
        wind_speed = current_weather_data['wind']['speed']
        city_name = current_weather_data['name']
        country = current_weather_data['sys']['country']
        
        # Convert timestamp to human-readable format for sunrise and sunset
        # Use timezone.utc to create timezone-aware datetime objects
        utc_timezone = timezone.utc
        sunrise_time = datetime.datetime.fromtimestamp(current_weather_data['sys']['sunrise'], tz=utc_timezone).strftime('%I:%M %p')
        sunset_time = datetime.datetime.fromtimestamp(current_weather_data['sys']['sunset'], tz=utc_timezone).strftime('%I:%M %p')
        
        timezone_offset_seconds = current_weather_data['timezone']


        # Fetch forecast data
        forecast_response = requests.get(forecast_url)
        forecast_response.raise_for_status() # Raises HTTPError for bad responses
        forecast_data_raw = forecast_response.json()

        # Process forecast data (limit to first 8 entries for next 24 hours, 3-hour intervals)
        processed_forecast = []
        # Get the current time adjusted for the city's timezone
        current_utc_time = datetime.datetime.now(utc_timezone)
        # We process based on UTC time from OpenWeatherMap to ensure consistency
        # and then adjust for display in the frontend if needed.

        # Filter forecast for the next 24 hours, or the first 8 entries (3-hour intervals)
        for item in forecast_data_raw['list']:
            forecast_utc_dt = datetime.datetime.fromtimestamp(item['dt'], tz=utc_timezone)
            # Only include forecast items that are in the future relative to current UTC time
            # and within approximately the next 24 hours (8 entries * 3 hours/entry = 24 hours)
            if forecast_utc_dt > current_utc_time and len(processed_forecast) < 8:
                # Adjust forecast time to city's local time for display
                local_forecast_time = forecast_utc_dt + timedelta(seconds=timezone_offset_seconds)
                processed_forecast.append({
                    "timestamp": item['dt'],
                    "time": local_forecast_time.strftime('%I:%M %p'), # Format: 07:00 PM
                    "temperature": item['main']['temp'],
                    "description": item['weather'][0]['description'],
                    "icon": f"http://openweathermap.org/img/wn/{item['weather'][0]['icon']}@2x.png"
                })
            elif len(processed_forecast) >= 8:
                break # Stop after getting roughly 24 hours of forecast

        # Prepare the final data to send to the frontend
        formatted_weather = {
            "city": city_name,
            "country": country,
            "temperature": main_weather['temp'],
            "feels_like": main_weather['feels_like'],
            "humidity": main_weather['humidity'],
            "pressure": main_weather['pressure'],
            "description": weather_description,
            "icon": f"http://openweathermap.org/img/wn/{weather_icon}@2x.png",
            "wind_speed": wind_speed,
            "sunrise": sunrise_time,
            "sunset": sunset_time,
            "timezone_offset": timezone_offset_seconds, # Offset in seconds from UTC
            "forecast": processed_forecast # Add forecast data
        }
        return jsonify(formatted_weather)

    except requests.exceptions.HTTPError as e:
        # This catches errors from response.raise_for_status()
        error_message = f"API request failed for OpenWeatherMap: {e.response.status_code} - {e.response.text}"
        app.logger.error(error_message)
        return jsonify({"error": "Could not retrieve weather data. City might be invalid or API limit reached."}), e.response.status_code
    except requests.exceptions.ConnectionError as e:
        app.logger.error(f"Network connection error to OpenWeatherMap API: {e}")
        return jsonify({"error": "Failed to connect to weather service. Please check your internet connection."}), 500
    except Exception as e:
        app.logger.error(f"An unexpected error occurred during weather fetch: {e}")
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500


@app.route('/ask-ai', methods=['POST'])
def ask_ai():
    """
    Receives a user's question and weather/forecast context, then uses the Gemini API
    to generate a relevant response about the weather.
    """
    data = request.json
    question_from_frontend = data.get('prompt')
    current_weather_data = data.get('current_weather')
    forecast_data = data.get('forecast')

    if not question_from_frontend or not current_weather_data:
        return jsonify({"error": "Prompt or current weather data is missing"}), 400

    # Construct a more detailed prompt for the AI, including forecast data
    ai_prompt_context = f"""
    You are a helpful weather assistant. Here is the current weather information for {current_weather_data['city']}, {current_weather_data['country']}:
    Current Temperature: {current_weather_data['temperature']}°C (feels like {current_weather_data['feels_like']}°C)
    Current Description: {current_weather_data['description']}
    Humidity: {current_weather_data['humidity']}%
    Pressure: {current_weather_data['pressure']} hPa
    Wind Speed: {current_weather_data['wind_speed']} m/s
    Sunrise: {current_weather_data['sunrise']}
    Sunset: {current_weather_data['sunset']}
    Current Local Time in {current_weather_data['city']}: {datetime.datetime.fromtimestamp(datetime.datetime.now(timezone.utc).timestamp() + current_weather_data['timezone_offset'], tz=timezone.utc).strftime('%Y-%m-%d %I:%M %p')}.

    Here is the forecast for the next 24 hours (3-hour intervals):
    """

    if forecast_data:
        for f_item in forecast_data:
            ai_prompt_context += f"- At {f_item['time']}: Temperature {f_item['temperature']}°C, Description: {f_item['description']}\n"
    else:
        ai_prompt_context += "No detailed forecast data available for the next 24 hours."

    ai_prompt_context += f"\nUser's question: \"{question_from_frontend}\"\n\n"
    ai_prompt_context += "Answer the user's question concisely and accurately based on the provided current and forecast weather information. If the question asks about a time beyond the provided forecast, state that. If the question is not directly about weather or the provided data, politely state that you can only answer weather-related questions based on the available data. Answer in the same language as the user's question if possible."


    gemini_api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    chat_history = [{"role": "user", "parts": [{"text": ai_prompt_context}]}]
    payload = {"contents": chat_history}

    try:
        response = requests.post(gemini_api_url, json=payload)
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        gemini_result = response.json()

        if gemini_result.get('candidates') and len(gemini_result['candidates']) > 0 and \
           gemini_result['candidates'][0].get('content') and \
           gemini_result['candidates'][0]['content'].get('parts') and \
           len(gemini_result['candidates'][0]['content']['parts']) > 0:
            ai_response_text = gemini_result['candidates'][0]['content']['parts'][0]['text']
            return jsonify({"response": ai_response_text})
        else:
            app.logger.warning(f"No valid response from AI: {gemini_result}")
            return jsonify({"error": "No valid response from AI. Please try again."}), 500

    except requests.exceptions.HTTPError as e:
        # This catches errors from response.raise_for_status()
        error_message = f"API request failed for Gemini: {e.response.status_code} - {e.response.text}"
        app.logger.error(error_message)
        # If it's a 403 Forbidden specifically, suggest API key check.
        if e.response.status_code == 403:
             return jsonify({"error": "Failed to connect to AI service. Please ensure your Gemini API key is correct and valid."}), 403
        return jsonify({"error": "Could not get AI response from service."}), e.response.status_code
    except requests.exceptions.ConnectionError as e:
        app.logger.error(f"Network connection error to Gemini API: {e}")
        return jsonify({"error": "Failed to connect to AI service. Please check your internet connection."}), 500
    except Exception as e:
        app.logger.error(f"An unexpected error occurred with AI: {e}")
        return jsonify({"error": f"An unexpected error occurred with AI: {e}"}), 500


if __name__ == '__main__':
    # No environment variable checks here, as keys are directly set above.
    app.run(debug=True)
