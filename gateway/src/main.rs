use std::time::Duration;

use chrono::Local;
use pancurses::{endwin, initscr, noecho, Input};

use log::info;

use rand::seq::SliceRandom;
use rand::thread_rng;
use rdkafka::config::ClientConfig;
use rdkafka::message::OwnedHeaders;
use rdkafka::producer::{FutureProducer, FutureRecord};
use rdkafka::util::get_rdkafka_version;
use serde::Deserialize;

use clap::Parser;
use serde_json::json;
//mod example_utils;

#[derive(Parser)]
#[clap(version = "1.0", author = "T <noreply@sysarcher.github.io>")]
struct Opts {
    #[clap(short, long, default_value = "gateway.toml")]
    conf: String,
}

#[derive(Debug, Deserialize)]
struct Config {
    broker: String,
    topic: String,

    messages: Message,
}

#[derive(Debug, Deserialize)]
struct Message {
    list_of_msgs: Vec<String>,
}

#[tokio::main]
async fn main() {
    env_logger::init();

    let conf: Opts = Opts::parse();

    let config_file = std::fs::read_to_string(conf.conf).expect("path doesn't exist");

    let gateway_conf: Config =
        toml::from_str(config_file.as_ref()).expect("TOML may be malformatted");

    let broker = &gateway_conf.broker;
    let topic = &gateway_conf.topic;

    let (version_n, version_s) = get_rdkafka_version();
    info!("rd_kafka_version: 0x{:08x}, {}", version_n, version_s);

    // Create producer
    let producer: &FutureProducer = &ClientConfig::new()
        .set("bootstrap.servers", broker)
        .set("message.timeout.ms", "5000")
        .create()
        .expect("Producer creation error");

    // Setup Terminal
    let window = initscr();
    window.printw("Interactive Mode\n\r  Press any key\n");
    window.refresh();
    window.keypad(true);
    noecho();

    loop {
        match window.getch() {
            Some(Input::Character(c)) => {
                let possible_waste_classes = ['1', '2', '3'];
                if possible_waste_classes.contains(&c) {
                    window.addch(c);
                } else {
                    continue;
                }
            }
            Some(Input::KeyDC) => break,
            Some(input) => {
                window.addstr(format!("{:?}", input));
            }
            None => (),
        }

        let mut rng = thread_rng();
        let oispjson = gateway_conf.messages.list_of_msgs.choose(&mut rng).unwrap();
        let mut sjson: serde_json::Value = serde_json::from_str(oispjson).unwrap();
        sjson["on"] = json!(Local::now().timestamp() * 1000);
        sjson["systemOn"] = json!(Local::now().timestamp() * 1000);

        // SEND to KAFKA
        let _delivery_status = producer
            .send(
                FutureRecord::to(topic)
                    .payload(sjson.to_string().as_bytes())
                    .key(&format!("Key {}", 1))
                    .headers(OwnedHeaders::new().insert(rdkafka::message::Header {
                        key: "header_key",
                        value: Some("header_value"),
                    })),
                Duration::from_secs(0),
            )
            .await;

        // This will be executed when the result is received.
        info!("Delivery status for message received");
    }
    endwin();
}

// https://gist.github.com/rust-play/1c02d2c6fd64851bc1c5af08f115c388
/// [Link to playground](https://play.rust-lang.org/?version=stable&mode=debug&edition=2018&gist=1c02d2c6fd64851bc1c5af08f115c388)
#[allow(dead_code)]
fn escape(src: &str) -> String {
    use std::fmt::Write;
    let mut escaped = String::with_capacity(src.len());
    let mut utf16_buf = [0u16; 2];
    for c in src.chars() {
        match c {
            '\x08' => escaped += "\\b",
            '\x0c' => escaped += "\\f",
            '\n' => escaped += "\\n",
            '\r' => escaped += "\\r",
            '\t' => escaped += "\\t",
            '"' => escaped += "\\\"",
            '\\' => escaped += "\\",
            c if c.is_ascii_graphic() => escaped.push(c),
            c => {
                let encoded = c.encode_utf16(&mut utf16_buf);
                for utf16 in encoded {
                    write!(&mut escaped, "\\u{:04X}", utf16).unwrap();
                }
            }
        }
    }
    escaped
}

#[test]
fn test_escape() {
    let escaped = escape("你好，世界");
    assert_eq!(escaped, "\\u4F60\\u597D\\uFF0C\\u4E16\\u754C");
}
