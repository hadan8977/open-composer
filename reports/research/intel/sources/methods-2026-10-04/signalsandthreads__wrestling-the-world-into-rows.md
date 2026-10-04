source: https://signalsandthreads.com/wrestling-the-world-into-rows/
fetched_utc: 2026-10-04T18:13:59Z

Signals and Threads | Wrestling the World into Rows

      All Episodes

Listen in on Jane Street’s Ron Minsky as he has conversations with engineers working on everything from clock synchronization to reliable multicast, build systems to reconfigurable hardware. Get a peek at how Jane Street approaches problems, and how those ideas relate to tech more broadly.

Listen and subscribe:

Wrestling the World into Rows

with Eric Mannes

				Episode 29   |  

			September 2nd, 2026

BLURB

“Alternative data” is Wall Street’s name for information that comes from non-traditional
sources: satellite photos of parking lots, credit card panels, weather forecasts. Eric Mannes
has spent over a decade at Jane Street, first as a commodities trader and now helping lead
the firm’s alternative data team. In this episode, Eric and Ron talk about what it takes
to turn messy external data into datasets a trading strategy can rely on. Along the way,
they cover the day oil futures settled at a negative price and the systems that broke as a
result; the years when the commodities desk’s risk system was one very large Excel
spreadsheet; the hard question of what a company even is; and why better ML models raise
the value of careful data engineering.

SUMMARY

“Alternative data” is Wall Street’s name for information that comes from non-traditional
sources: satellite photos of parking lots, credit card panels, weather forecasts. Eric Mannes
has spent over a decade at Jane Street, first as a commodities trader and now helping lead
the firm’s alternative data team. In this episode, Eric and Ron talk about what it takes
to turn messy external data into datasets a trading strategy can rely on. Along the way,
they cover the day oil futures settled at a negative price and the systems that broke as a
result; the years when the commodities desk’s risk system was one very large Excel
spreadsheet; the hard question of what a company even is; and why better ML models raise
the value of careful data engineering.

Some links to topics that came up in the discussion:

Figgie

Adverse selection

2020 Russia–Saudi Arabia oil price
war

Dual-listed company

“LAMBDA: The ultimate Excel worksheet
function”

Trino

The Bitter Lesson

Learn more about Jane Street’s internship
program.

Apply for Data Engineering roles at Jane Street

CONTENTS

00:00:02 – Three summers and an anti-inductive market

00:03:37 – Mock trading and Figgie

00:08:47 – From intern to commodities trader

00:11:54 – Futures, multipliers, and metadata

00:18:53 – The day crude oil went negative

00:22:53 – Desk devs and a very large spreadsheet

00:26:23 – Excel as a functional programming language

00:30:40 – Translating between traders and engineers

00:34:19 – What counts as alternative data

00:36:46 – Starting the alt data team

00:44:12 – Data strategy and the vendor market

00:49:52 – Data infrastructure vs. data engineering

00:53:02 – What even is a company?

00:56:51 – Parking lots vs. credit card panels

01:01:30 – Point-in-time data and vendor revisions

01:06:05 – What AI changes about data work

01:12:47 – Build vs. buy

01:18:44 – Hiring data engineers

TRANSCRIPT

Three summers and an anti-inductive market (00:00:02)

Ron

It’s my pleasure to introduce Eric Mannes. Eric has been at Jane Street for about a decade
and he’s had a really interesting range of roles here spanning trading and technology and
these days thinking a lot about alt data, which is a lot about what we’re going to talk
about today. So thanks for joining me.

Eric

Thanks for having me.

Ron

So maybe to start with, I’d just like to hear a little bit more about how you got to Jane
Street in the first place.

Eric

I studied math in college and I looked at what many of my peers did. And a lot of them
were going into academic research, perhaps in Boston. A lot of them were going into tech
often in San Francisco and some of them were going into finance, usually in New York City.
And so I thought, well, I have three summers in undergrad and I’ll just spend one summer
trying each of these. And at the end I was like, Jane Street is by far the most
interesting of these and the best fit for me, so I’ll do that.

Ron

So what about the trading experience struck you as so interesting?

Eric

So I was a trading intern and I was really struck by how much I was learning.

Ron

I guess one of the interesting things about trading is by and large, it’s not a thing that
anybody knows. We hire software engineers and they’ve often done software engineering in
other places, but the vast majority of people who come here have no experience in the
trading world.

Eric

Right. And so there was nothing really outside that had given me practice trading or any
depth in thinking about markets. And when I came here, I was struck by how much time
people at Jane Street spent teaching the interns about the fundamentals of how markets
work, about concepts like adverse selection, how to do research well. And people use the
word anti-inductive environment of when you discover some effect in physics, it’s not like
that effect goes away. In finance, the things that you find, the patterns that you find
often get discovered and competed away over time and the things that you knew stop being
true or as important. And so you have to keep discovering new things.

Ron

Right. And then what remains looks ever more and more like a random walk. And this is why
actually our signals-to-noise ratios are kind of miserable because there’s this whole
system whose job is to extract signal from the system and have it look more like a kind of
pure representation of our remaining uncertainty, which is sort of by its nature looks
more random.

Eric

Right. And when you act in this system, other people respond and change their behavior in
ways that weren’t visible in your training data.

Ron

Yeah. An amazing thing about the world of trading is it’s this interesting compromise and
incentive system that rewards people for learning things about the world, but does it in a
way that essentially forces them to give some of that information up. So you have this
kind of information discovery system where all of these people trading and competing with
each other feeds information into the markets and then the markets now are a kind of more
reliable gauge for what things are worth, which tells you all sorts of things about what’s
happening in the world.

Eric

I think that felt very real on commodities and in my current work on alt data where we are
looking at data from the real world to understand it better and incorporate that
information into market prices.

Mock trading and Figgie (00:03:37)

Ron

So you said that you were struck by the amount of effort that people put into teaching,
and I think teaching really is an important thing here. And actually I think one of the
interesting facts about Jane Street, which is maybe not obvious from the outside, is the
insane amount of effort that goes into the internship because we think getting great
people is incredibly important and we’ve kind of put almost a pathological amount of work
into making the internship a really great experience. But I’m kind of curious, how did you
feel like that played out? What were examples of the kinds of things that happened in the
internship that you felt like taught you more about how to think about markets and what
the job was like?

Eric

One important part of the internship was mock trading or trading at low stakes. You can
talk about good decision making in the abstract, but -

Ron

No replacement for actually trying to do it live.

Eric

Yeah. There’s no replacement for actually trying to do it live. Doing it in a context
where you kind of commit to something and there are consequences to what you choose I
think provides useful feedback.

Ron

And I think this goes back to the fact that very early on at Jane Street, we felt like the
early people here learned an enormous amount from being on the trading floors and in this
kind of live trading environment and the nature of what trading is and how it works and
the basics of adverse selection and information flow and all of that. But you can’t
actually send everyone back to the trading floors. Many of them don’t exist anymore. So
what does it actually look like being in a mock trading session?

Eric

Yeah, this has improved a lot over time, but one thing that we do is we do have a
simulated stock exchange where interns can trade and we’ll have these one or two hour
scenarios that kind of distill some important trading concept or thing that happens in
real life into a time-boxed toy model of it. So what’s an example? We have a trading card
game, not trading card game. Well, it is trading and it is a card game.

Ron

Close enough.

Eric

Called Figgie where you and three other players each have some private information about
what the different cards in the game are worth and you do trades based on that information
and you pay attention to what other people are doing, what information that they have that
is probably causing them to behave in that way and think about how you should update what
you’re doing or the trades that should happen when you and someone else have different
information or reasons to value the same thing differently. It also gets people used to
market making language and putting themselves out there and being willing to buy or sell
spades for seven chips. And I think getting people comfortable with making decisions under
uncertainty in these kind of controlled low stakes environments, I think is good practice
for doing it in the real world without the psychological pressure that would normally get
in the way. Have you read the book Ender’s Game?

Ron

I have.

Eric

Right.

Ron

Classic.

Eric

Yeah. We can’t actually do that in real -

Ron

Have people do mock trading and then slowly at some point discover that mock trading is
actually real trading.

Eric

Right. I think for licensing, legal, supervisory reasons, it’s problematic. But it is
easier to teach intuitions about trading in this game-like environment where you can try
things and see the outcome that isn’t quite the heat of battle.

Ron

Right. And I guess like a game, there’s an adversarial component to it. It’s not like the
markets aren’t a zero sum game, they’re like a positive sum game. In the end, people all
in benefit from participating in the markets, but small positive sum. And so if player A
is winning a lot, then player B, who they’re trading with is losing a lot and that gets
reflected in the kind of game structure as well, I imagine.

Eric

Yeah. Identifying when you are doing a positive sum trade with someone versus situations
where you and someone who is just as smart as you disagree about some fact of the world.

Ron

And one of you is wrong.

Eric

One of you is wrong and you should think hard about why you think what you do.

Ron

Right and why you’re not the one who’s making the mistake.

Eric

That’s right.

From intern to commodities trader (00:08:47)

Ron

Okay. So you learned a lot through this internship and you decided actually this is the
thing that you wanted to do. What was it like going from having been an intern to actually
being here as a trader?

Eric

It was even more interesting than I expected because there were all of these real life
trading decisions and strategies that we couldn’t get into the details of for IP reasons.
But I felt like I was learning a lot during the internship. And then once I got to Jane
Street, we could talk about the trades that we were actually doing as a firm and the
decisions that we were making as a firm. And so I started off on the commodities desk
learning to trade oil and natural gas ETFs and index ETFs, which are about 50% oil and
energy related products. And looking at the trades that we were doing and thinking about
did they make sense? Were they good trades? Why were we doing them? If they were good
trades, why didn’t we do more of them? And if they were bad trades, why did we do so many?
All of this happened sitting next to a mentor who was an experienced trader who had been
here a long time. And a bunch of trades would happen and then he would say, “Okay, well,
what do you think we should do here? How should we change our behavior?” I would think for
a bit and say something and he would say, “Well, okay, we’re doing something else.” And
then work through with me like, “Okay, well, you should also take into account this, that,
and the other thing. And over time, through working through all of these examples and
getting this feedback, you learn to make better decisions in these contexts.

Ron

How long do you feel like it took until you were able to make positive suggestions that
actually would influence the trading that we do?

Eric

I don’t know. A couple months.

Ron

I suppose in the small -

Eric

I think in the small pretty quickly.

Ron

Right because there’s just stuff that other people don’t have time to pay attention to and
you can. You don’t have to be better than everybody else to add value.

Eric

Right, you can become Jane Street’s expert on this one ETF and its trading dynamics or
think really hard about something that no one else at the firm has yet and have some
interesting suggestions. And over time, the scope of what you are comfortable doing on
your own increases. At first, it’s like, “Hey, I think we should make this small change.
What do you think?” And you’d get comfortable with doing that and eventually get more
comfortable making the bigger decisions on your own, but reaching out and gathering more
input when you weren’t sure.

Futures, multipliers, and metadata (00:11:54)

Ron

You said that you could become Jane Street’s expert on some particular corner. Can you
give me an example of some little corner of the world that at some point you became the
local expert in?

Eric

Oh, man.

Ron

We’re going back a lot of years.

Eric

I think at the time our trading systems were pretty slow and we were rolling out a new
generation of trading systems that were considerably faster by two orders of magnitude or
something, but still slower than the frontier and slower than we are today. Someone had to
think about how to optimize our use of these systems and analyze where we were gaining
from speed or what opportunities we were missing. And I don’t know, who should do that?
Eric’s new, he has time. I think another thing is I spent a lot of time thinking about
futures and their multipliers and the risk that you have when you trade a future and how
that’s different from when you trade a stock.

Ron

Yeah, this seems like a dumb corner of the world, but also one that I’ve spent a weirdly
large amount of time over the years thinking about where it’s like you get used to trading
equities and it’s like, “This is great. When I want to think about the risk of the trade,
a starting point is the cash flow. What’s the cash flow to trade? It’s just the product of
the price and the size. This is so nice.” And then turns out, not so much in futures.

Eric

Right.

Ron

And maybe it’s worth saying, what is a future? A future is an agreement in the future,
hence the name to exchange some money based on some other benchmark that this thing is
tied to. So the S&P 500 futures are tied to the closing value of the basket of S&P 500
stocks at a particular point in time, I think.

Eric

No, I think it’s actually the opening prices.

Ron

It’s the opening price. Okay. Shows what I know.

Eric

On the third Friday of the month.

Ron

Amazing. But on which exchange?

Eric

Yeah. When you buy a crude oil future, you agree to pay some money for either the value of
some index related to oil prices or a thousand barrels of oil delivered to you in Cushing,
Oklahoma.

Ron

So-called physical delivery.

Eric

Yeah, physical delivery or live cattle where actually sometimes the cattle are delivered
dead, but tens of thousands of pounds of beef. We are generally financial players who did
not want to take delivery of a thousand barrels of oil in Cushing, Oklahoma. I’ve never
been there. And I don’t know where I would store the 20,000 pounds of beef. When you buy a
future, you put up some margin with the exchange and if you are long and the future goes
up, the exchange credits some money to you. When the future goes down, the exchange
removes some of your money and possibly asks you to put up some more margin so that they
know that you’ll be able to pay off losing bets. Another thing you can trade is the spread
of two futures. You get long one and short another. So the CLU6-CLV6 spread, if you buy
that on the CME, you get longer crude oil futures deliverable in September and shorter
crude oil deliverable in October. And if you trade S&P 500 future spreads, you have the
opposite sign convention. But in either case, your position, sorry, the thing you trade
decomposes into two different positions rather than the one thing you bought.

Ron

Right. And I guess the point here is that all of this is one level more abstract than the
underlying things are being traded. So instead of trading the outright thing, you’re
trading this future on the thing. And then there’s a bunch of conventions and some of the
conventions are about it has a name that says what the two legs of the spread are, but
which one is positive and which one is negative? Depends on the future. And you can’t just
look at the notation for sure and know the answer. And then where we started, this other
crazy thing called the multiplier, which actually tells you the real size of this.

Eric

Right. When you pull up the ticker for some future, say crude oil, you’ll see a price for
one barrel of crude oil or one pound of live cattle. But actually when you buy the
contract and take delivery, you get a thousand barrels and the notional value is a
thousand times of the quoted price. And different sources will, depending on where you’re
getting your pricing from, you will get different prices and different multipliers and
sometimes different currencies. Someone will quote in dollars and another person will
quote it in cents.

Ron

It’s a small matter of a factor of a hundred.

Eric

Yeah. And as long as you always keep track of which prices correspond to which multipliers
and never mix up the two, you won’t accidentally trade a hundred times less or much worse,
a hundred times more than you intended.

Ron

Right and so this matters from a risk perspective. Ideally, we’d like to have relatively
simple systems that are stepped back from the details of the trading strategy, which put a
kind of outside envelope on the risk that the systems are taking. And that’s way easier if
you actually know what’s going on. But what you’re pointing to is this whole, what we call
a metadata problem of actually understanding the details of how these contracts actually
work. And it’s just made much more complicated by the fact that the world is full of huge
amounts of unnecessary complexity of different conventions and different details of how
these things are quoted in different contexts.

The day crude oil went negative (00:18:53)

Eric

Yeah. And you have assumptions that are baked into your trading and risk systems, like
this price will always be positive, that turn out to not be true. On April 20th, 2020, the
price of the almost expiring crude oil future on the CME settled at a negative price. And
you’d always think, well, goods are good. They’re not -

Ron

They’re worth something.

Eric

They’re worth something.

Ron

You should pay for them. They’re not bad.

Eric

You should pay a positive amount of money for them. And that breaks a lot of assumptions.

Ron

But how can it happen? How can a crude oil future be worth negative? Goods normally are
good. What happens?

Eric

Yeah. So that crude oil contract was for oil delivered to a particular place at a
particular time. And at the time in Cushing, Oklahoma, storage was getting full. There
wasn’t much place to put the crude. Supply of oil everywhere was high and demand for
obvious reasons was considerably lower than usual.

Ron

If you remember April 2020.

Eric

If you remember April 2020. Yeah. And that added up to, well, if you were long, what would
you do with it? And this isn’t quite true because for one day the settlement price was a
negative number. And the final settlement price of this contract was positive. In the end,
people were willing to pay positive dollars for crude. But on April 20th, there just were
not enough people willing to step in and say, “I will pay money for this thing.”

Ron

And when all of your systems had assumed this price was positive for a long time, maybe
your trading systems do not have a great day.

Eric

Right. Maybe the people who would normally provide to these moves weren’t able to send
orders because their order entry system didn’t know what to do with a negative 100%
return. Also, if you were modeling other products based on the price of crude oil on that
day, how are you modeling oil companies or everything else? Should you be using that
negative crude future? I’m not sure.

Ron

Right. And I guess just zooming out for a second, this points to a thing about trading,
which is some of trading is thinking hard about the technology stack and the math and the
modeling. And some of it is just diving into a bunch of grotty detail of how does the
world actually work? What are the mechanics of the markets and the systems and the amount
of storage space there is in Cushing, Oklahoma? And all of those things can play in. And
this is a general fact about trading is lots of different kinds of things about the world
can flow into the trading process. I think sometimes people who hear about Jane Street
think it’s all about high tech, high performance, smart math models and stuff and that
stuff is all real and part of it. But there’s also a lot of detailed engagement with how
the world actually works that also plays into being an effective trader.

Eric

Right. And I think that’s true across all of our businesses, but it is very true in
commodities where the things that you are buying and selling are connected to the physical
world, oil and wheat and things that people actually physically produce and consume.

Ron

And occasionally deliver to you.

Eric

And occasionally deliver to you. Yeah.

Desk devs and a very large spreadsheet (00:22:53)

Ron

So in addition to thinking about all of these kind of trading-focused concepts on the
desk, you also spent a bunch of time thinking about technology on the desk. Can you say a
little bit more about what that was like?

Eric

Right. At the time, I think how Jane Street approached developing technology for trading
was having a bit of a phase shift. We went from having developers who primarily worked on
the core infrastructure that undergirded our trading, the trading systems, the market
data, bookings pipeline, that sort of thing, while traders, people on our commodities desk
and our domestic ETFs desk would plug into those systems, but do less systems development
themselves. And at that time, I guess we finally felt that we had enough breathing room to
say, well, what if we built commodity specific systems to help address the unique problems
with trading commodities?

Ron

And this is a thing that happened not all at once, but at different desks at different
points of time. Some desks were more technical in their needs, some were less. And so this
kind of desk dev phenomenon unrolled over a period of years as we got enough capacity. And
now every desk across the firm has embedded desk devs because you just need it everywhere.

Eric

Right. But at the time it felt like, well, this is working here. We should try this
elsewhere too. And when we were starting to build out the commodities desk dev team, we
needed someone from trading to help think about it. And I was relatively technical having
done my tech internship for one of my free summers. And having learned OCaml in OCaml
bootcamp, I got involved with that. And that involved things like thinking about how we
keep track of our risk or exposure to different commodities. If you’re looking at your
positions in energy products, you could look at it at a very high level or you could look
at just oil and related products. You could look at West Texas Intermediate crude oil
alone, or you could look at the November contract of this one commodity and you need to be
able to shift from level to level all at once and be able to dig into exactly where your
exposure to these was coming from. And we’d been doing this before. It was in a large
Microsoft Excel spreadsheet, uscommoditiesrisk.xlsm. And you’d press a button and it would
pull in data about our trades and positions and crunch some numbers. One, sometimes it was
slow. Two, it was something that had built up over time and was built by people who were
very good at using Microsoft Excel and very knowledgeable about commodities, but were not
by and large software engineers and building it up again from first principles and making
sure that you got the foundation right to something that we could really trust, let us
build more and more ambitious things on top of that than we were able to build when it was
an Excel spreadsheet that ran slowly and worked, except occasionally when it didn’t.

Excel as a functional programming language (00:26:23)

Ron

I feel like people who don’t use Excel much probably underestimate how good it is. And
then when you’ve used Excel a lot, you have a really good sense of like, oh my God, what
the limitations are. Excel in many ways is kind of great. It gives you great ways of
visually inspecting and understanding the data. It’s extremely flexible. It’s actually
quite easy to debug in important ways. But yeah, there are profound performance
limitations. What else actually was bad about doing it in Excel? What were the downsides?

Eric

Yeah. I should say before all of this that I love Microsoft Excel and I don’t use it very
much anymore. But we like functional programming here. Excel formulas, spreadsheet
formulas are I think the world’s most widely used functional programming language.

Ron

For sure.

Eric

I think Excel has lambdas now.

Ron

It does. And let bindings.

Eric

And let bindings. Yeah.

Ron

I think thanks to Simon Peyton Jones and some other people at Microsoft who helped build
it.

Eric

Yeah. When you write Python code, usually you have the code in front of you, the logic in
front of you, but the data is hidden away until you write something that visualizes it for
you. And with Excel, the data is front and center and the logic is hidden in the back. And
that’s pretty useful in a lot of cases. People are making decisions about what to do based
on the data that they see. So what were the problems here? Performance was sometimes fine,
sometimes at critical moments, quite bad. You aren’t just writing the cell formulas
yourself. You are writing Visual Basic to construct the spreadsheet that you use.

Ron

But this is like cell meta programming. You are writing a program that writes a program
that’s laid out in the sheet.

Eric

Yeah, you press a button that runs a nest of Visual Basic macros that initialize a sheet
with all of our positions and trades and the code on top to analyze them. And Visual Basic
is okay. No, I mean it was impressive what we were able to do with it. But having a
type-safe language where the compiler can catch a lot of your mistakes where you can write
robust tests and interfaces is an advantage that many programming languages have that is
hard to do in Visual Basic. Also version control, hard to do version control in a
spreadsheet.

Ron

Excel is not optimized for that.

Eric

I once wrote an Excel Grep tool that was just a firm utility for searching through
spreadsheets because opening them up one at a time and in Excel and control F-ing first
through the Excel formulas and then through the Visual Basic is impractical.

Ron

No way to live.

Eric

Yeah. And if you need to do large migrations of many spreadsheets at once, which we
sometimes did, it helped to be able to search them. Maybe related to the lack of version
control is that things just build up. Someone puts some throwaway cell formulas for
analysis in one corner of one sheet and then it’s just there forever. So you get to a
point where no one fully understands what it’s doing, though some people know a lot and
are pretty sure. And it’s hard to rebuild that model of how the spreadsheet works and
become confident that there are no issues.

Translating between traders and engineers (00:30:40)

Ron

So that itself I feel like makes the process of replacing it hard, right? Which is like
there’s this spreadsheet, it’s an artifact, it has a lot of embedded domain knowledge that
actually no human knows all of anymore. And then what was your role in trying to help
bridge the gap between the spreadsheet that did the thing and then the piece of software
that we were going to build to replace it?

Eric

Right. So a lot of what I did was translating between the domain understanding that the
other traders and I had and a description of the domain and the problem that a software
engineer can work with and build a robust system around. Rather than someone saying,
“Well, I want this and it should do that and that and the other thing.” Distilling that
down into what we’re fundamentally trying to do, which is model the risk exposures of our
commodities desk and how we are trying to do it, the input sources and how they should fit
together, what the basic atoms are. And we built up that model of the thing we were
building, the flow chart of how all this data fit together and turned into the end result.
And then people were able to just confidently build some part of it knowing that it would
fit together into the whole correctly.

Ron

I imagine it’s much better for the software engineers if they don’t just have a spec, a
narrow spec of a thing to build, but also they understand the background and the domain in
a way that’s a little more kind of actionable and fills out their understanding of the
world.

Eric

Yeah. And information flows the other way as well. I think the domain experts who are not
themselves software engineers don’t understand how good things can be if we build the
right software for it. I have suffered for years doing things in this way because there
weren’t tools to help me do it better. And I’ve gotten so used to it that I don’t realize
I need something better.

Ron

One of the characteristics of many Jane Street traders is high pain thresholds. People are
willing to deal with pretty messy things and pretty unpleasant things. If I have to knock
my head on the table three times and slap my cheek in order to cause money to come out of
the machine, they’ll just do that all over and over and over.

Eric

Yeah. And someone who makes a good desk dev at Jane Street can say like, “No, there’s no
way you should be doing it that way”. If we built this tool, it would be much easier to do
these studies that are either difficult to do now or that no one would bother doing now
because we don’t have the right language for working with them.

Ron

So part of what you need to convey to the traders is a better cost model. Understanding
what’s possible and understanding that some improvements are maybe way cheaper than they
imagine and some are more expensive than they imagine.

Eric

It’s not just the costs. You can have great ideas for what we as a desk or as a company
should be doing differently. It’s like I am someone with this particular set of skills and
knowledge and my job is to help Jane Street do the best trades.

What counts as alternative data (00:34:19)

Ron

All right. So you’re no longer on a trading desk. Today you help lead our alt data effort.
Can you say more about what is alt data and what is it at Jane Street?

Eric

Yeah. So out in the world on Wall Street, alternative data is data that you use for the
investment process that isn’t normally used in the investment process.

Ron

It’s an unstable naming convention.

Eric

Right. If enough people use it, does it drop its alt moniker? The canonical example of
alternative data is a satellite photo of a Walmart parking lot. You take a photo of the
parking lot, you see how many cars are there. If there are a lot of cars, they have a lot
of customers and they’re doing well. If the parking lot’s empty, that’s a bad sign. And in
contrast, there’s traditional data, orders and trades on exchanges, basic information
about instruments, stocks. Imagine Warren Buffett reading an annual report and thinking
about the balance sheet and income statement. That’s traditional data. And at Jane Street,
a lot of data is alternative. The satellites are alternative. The company filings with the
SEC are alternative. The things that are traditional are the real-time market data from
exchanges, the basic instrument metadata that we need in order to run our trading and risk
systems and booking and so on.

Ron

Back to the multipliers.

Eric

Yeah. And it’s based on the path dependent evolution of Jane Street’s trading, starting as
a market maker and then expanding into adjacent areas.

Ron

In fact, it’s reflected in team structure. We have a market data team that does that kind
of live data from exchanges and from other places and we have a metadata team. And then we
have this alt data team, which in some sense is picking up the rest of that kind of value
that you get from other sources of information. And then how did you get involved in this
space?

Starting the alt data team (00:36:46)

Eric

How did I get involved in this space? So at Jane Street, you can do whatever you want, as
long as it’s the right thing to do. Your job is not to maintain this one system or to
trade this one product. Your job is to help Jane Street maximize its P&L over the long
term. What that means is that if you see a problem that you think is important to solve,
what’s stopping you from solving it? I mean probably you should talk to other people and
make sure that this is a real problem and that it is worth fixing and it is worth your
time fixing. And at some point I was thinking about a bunch of different data related
things at Jane Street and realized that we were failing to find trades because our data
was too hard to work with because external data specifically was too difficult to work
with. Our infrastructure for streaming in real time and surfacing for historical studies
of the real time market data was great and had lots of engineers and specialized
infrastructure while the data infrastructure for all that other data was kind of weaker.
It was annoying to just get data in the walls of Jane Street, both from a contractual
perspective.

Ron

There was no alt data team at the time.

Eric

There was no alt data team.

Ron

So how did it happen? Where was the work done? Who was doing the work? What the shape of
all that?

Eric

Yeah, I think when we started it was me and a small number of devs, including Jacob, who
was on the podcast earlier and a very small number of data engineers. And we had three
areas we were focusing on.

Ron

Wait, but I think you’re going ahead like before that. I was sort of thinking the early
version of this I assume was just kind of crowdsourced by the desk of when there were data
sources.

Eric

Sure. We were using external data before we had an alt data team. And the work of building
the data pipelines and integrating that data would be done by whoever was around and
available at the time. So someone on the commodities desk would say, we want this data set
and our data vendor management team would go out and buy that dataset and a dev or a
trader or a trading desk operations engineer would bring in the data and put it somewhere,
maybe in some corner of a large NFS tree or shared file system, maybe in a database, but
which one? And the result would be, I don’t know, 60% as good as it could be.

Ron

And I guess this process was happening some on the commodities desk... Eric Yeah,
some on the commodity desk. Ron Some on the domestic ETF desk, some on whatever.
Various different desks, reinventing the wheel, doing slightly different versions of it.

Eric

By people whose job was not primarily thinking about how to build data pipelines well, who
were not thinking about what could be shared between those processes, who sometimes, but
not always thinking about how should people around the firm, not just in the use case that
I’m thinking about right now, be using this data. And thesis was that we could have a
centralized team try to do that, think about a centralized team to source some of these
weirder alternative data sets to build better tools for building these data pipelines and
to maintain some of these data pipelines, especially ones that had firmwide impact that
would be used in a lot of different places.

Ron

So how did you go from the recognition of, man, this is kind of a mess. People are
generating data sets in messy ways, don’t have great ways of distributing them, don’t have
good technology for serving the data, don’t have good ways of cleaning the data, don’t
have good shared practices. And so we have less good data that is just harder to convert
into valuable trades and it’s therefore worth less money. So that seems like a key
observation. How did you go from that observation to actually doing something about it?

Eric

So sure, you’ve identified a big problem and many people at the firm would agree that it
was bad in all these ways, but there are lots of things we can make better. Why this one?
Part of it was we’d experiment, we’d do something on a small scale and the results would
work well, so we’d do it more. We’d find one particularly basic but annoyingly difficult
to use data set and make it easier to use, think very hard about it, and people would
start using that new thing. And lo and behold, there were effects that they were not able
to find when the data was really difficult to work with that they were suddenly able to
find when the data was easy to work with and when someone had thought really hard about
those edge cases and put in the work of understanding the data model and so on.

Ron

So basically incrementally go do some things, make it better, demonstrate that it’s worth
money. You see the P&L coming out the other side. And after a while it just becomes clear
to everyone that like, “Oh, we could use a lot more of this.”

Eric

We could use a lot more of this. And so we hired our first data engineer at Jane Street
ever in 2023. And the feedback has been like, oh, we could really use a lot more data
engineering help actually. The more people work with data engineers and see the results
from good data engineering work, the more they are excited to apply that toolkit to other
problems I guess by informing people about how much easier it is to build a good quality
data sets than it was before and the results that we’re able to get in doing so they want
to do it more.

Ron

So induced demand.

Eric

Induced demand. Yeah.

Ron

So just to step back, so we went in 2023 from having our first data engineer. How many do
we have now?

Eric

Let’s say 20 something.

Data strategy and the vendor market (00:44:12)

Ron

Got it. So a much bigger effort. As it’s grown out, I’m kind of curious, what’s the
structure of the team? You mentioned data engineers, but I don’t think alt data is just
data engineers. So how does the team break down into different kinds of people with
different kinds of expertise?

Eric

One group is data strategy and that’s not engineering at all, but their job is to
understand what data Jane Street needs and what data is out there in the world. And then
if there’s a match, get the data for us so that we can do good data engineering to it. And
so internally that looks like talking to our different trading desks and understanding
what problems they are trying to solve and what problems they could solve with better
data. The external part involves getting out there and showing up and -

Ron

But it’s another case where you have to understand grotty details of the real world.

Eric

Yeah. We go to conferences where we’ll talk to data vendors. So there are these data
catalog companies, one example of which is Neudata. And the data catalog companies, they
have analysts who learn about the different kinds of data that are being offered to the
financial industry and document them somewhere. And data consumers like us pay for a
subscription to that catalog. And they’ll also organize these conferences where data
buyers show up, data sellers show up. They’ll have speed dating between the buyers and
sellers where you’ll read all these profiles and you’ll say, “I want to talk to these
ones.” And then they match you and you have 10, 15-minute dates in a row where they
explain their product to you and you ask the questions that you have and try to figure out
whether this is some data that would make sense.

Ron

Do you sit there with a glass of Chardonnay as you’re...

Eric

Yeah, usually it’s drinks after. And you go there and some of them you say, “Well, this
was interesting, but I don’t think there’s a match here.” And others you say, “We should
talk more. Can I get your number, your business card?” So that’s one way of meeting.

Ron

So this is a weird two-sided market, right? There’s buyers and sellers. Who are they?
First of all, who are the buyers? Because obviously people like us, trading firms. Is it
all trading firms who are the buyers?

Eric

Yeah, so I think there are a lot of trading firms that don’t look like us. There are hedge
funds, whether big multi-strats or small asset managers, banks, participants who want data
for their investment decisions and analysis or research. Some of them are expanding into
other kinds of buyers like private equity or whatever. The sellers vary. There are
satellite providers say who have satellite data.

Ron

So you can see the Walmart parking lot.

Eric

So you can see the Walmart parking lot. So there are big companies that own lots of data
sets over lots of verticals. The Bloomberg, S&P, LSEG Refinitivs of the world. There are
companies that focus on a specific kind of data, consumer transaction data. There are
companies that happen to have data from their business. Either they’re a satellite company
and they have satellites, or they’re a company that provides goods or services and they
have exhaust data and they think, maybe someone would want to buy this.

Ron

Do you actually have a sense of how much of this big market for data has trading of
various forms or financial companies for various forms on the buying side and how much is
other stuff?

Eric

Some of this data is probably also used for targeting ads. Ron Sure. Eric And one
important difference between the trading use case and the ad use case is that we don’t
want to know who the individual consumers are.

Ron

Right

Eric

We want to know people are spending more at Lululemon. People are buying more Ritz
crackers. But apart from demographic information that might help us weight the data or
maybe information that would let us see, oh, people who buy this also buy that. We don’t
want to know -

Ron

Who the actual individual is?

Eric

Who the person is. While with advertising, I think it’s the point.

Ron

Right. As if you’re doing this kind of micro-targeting.

Eric

Yeah, if you’re doing the micro-targeting.

Data infrastructure vs. data engineering (00:49:52)

Ron

Okay, so let’s take a step back. So we just said one part of this is this data strategy,
which is thinking about the sources and the sinks, understanding places where data could
come from and places where data can be used internally and doing this kind of internal and
external kind of matchmaking process.

Eric

Yeah. Some of it is through catalogs, data sets that are advertised and exist. And some of
it is from thinking from first principles, what question am I trying to answer? And what
data could help me answer that question? And who might have that data? Whether they are
selling it right now or not.

Ron

So I guess there’s someone who you think might have data who isn’t selling it, but you can
go talk to them and maybe there’s a product they can make.

Eric

Yes. In addition to data sourcing, we have our data infrastructure, the tools for
ingesting and transforming data for monitoring our data pipelines, the building blocks
that people who are building data pipelines actually use.

Ron

Got it. And this is what looks maybe more like a straight ahead software engineering role?

Eric

Yeah, that is more like software engineering. Your product is software and systems and
services. And the people who do that are largely people we hired through our standard
software engineering pipelines. And then we have data engineering, where they’re also
engineers, but the product is a good data set. What they do is they build data pipelines.
They bring data into Jane Street’s walls and they transform it into the form that we need
in order to use it in research and trading. But they also have to learn a lot when doing
so. They have to understand how does this data set work? How does this data domain work?
What is this data actually modeling? They have to understand how we’re going to use the
data, understand how the data is produced and synthesizing all of that. Figure out, “Okay,
what should Jane Street be doing with this data?”

Ron

So you said a lot about what they need to understand, but I’d love to hear a little more
about what they actually do. Part of it you said is writing a pipeline and a pipeline
itself is just a kind of program. Some program that brings in and transforms and
regularizes the data into the shape that you need. But to what degree is that just a
mechanical matter of parsing and understanding what is the shape in which the bits have
been laid out? And to what degree do you need stuff that’s more in the domain and what’s
the shape of that work that you need to do that involves understanding more about the
data?

Eric

Some of it is mechanical, but we build tools to automate as much of that as possible. Part
of it is thinking about what does this field actually mean?

What even is a company? (00:53:02)

Ron

Maybe we could go into an example. What’s an example of some data source that has some
stuff that is on its base hard to interpret and then you go out and understand more about
the domain and can produce an easier to use version of that data.

Eric

So company financials are not alternative at all. They’re the opposite of alternative. In
the US at the moment, public companies publish their financial statements every quarter
and it’s published via filings with the SEC. Maybe a snippet is shared via press release
at around the same time. And you have all of this data about lines from a company’s
balance sheet or income statement and you want to turn that into some structured form that
we can do quantitative studies on top of.

Ron

So that’s rough. When you say structured versus unstructured, there’s a PDF or a big pile
of text and you want to convert that into morally rows in the table?

Eric

Yeah. And there are companies that will do this, that sell tabular versions of company
financials. Let’s start off with what even is a company? How do you know what a company
is? How do you know which financial statements are about the same company or about the
same financial period of a company? Some companies have these weird structures. I think
they’re called dual-listed companies where there’s company A and there’s company B, and
neither one is a parent company of the other, but they have the same management, the same
board often. And there is some, I don’t know, intercompany agreement that they have such
that owning them is economically equivalent.

Ron

So you have two things that are formally different companies.

Eric

Formally different companies.

Ron

And then in practice economically are the same thing.

Eric

Yeah. And so you think about edge cases like that. You receive data about something. Is it
one company? Is it both companies together? What is it exactly? And because you’re trading
on this, you associate it with securities. Does it apply to all of the securities of both
companies?

Ron

And this just kind of goes back into the metadata problem of there are all sorts of weird
company structures and different names for things and different naming conventions. And
sometimes you talk about the ISIN, which is the name of the thing internationally. And
sometimes there’s the SEDOL, which differs depending on which clearing system you’re in.

Eric

And which does the data apply to the company or a share class or a specific ISIN or a
specific listing?

Ron

There’s a million ways of expressing the names of things and there’s a bunch of complex
structural stuff that is kind of real, but also maybe you want to collapse when thinking
about it.

Eric

And then companies publish multiple versions of their financial statements. They’ll put
out one and then they might revise it or they’ll change their fiscal calendar or
accounting in ways that make A not completely comparable to B. Throughout this you have to
think through what data was knowable at what point in time and what features do I actually
need for our trading?

Parking lots vs. credit card panels (00:56:51)

Ron

I mean the metadata one is one that’s come up a lot in this conversation. Are there good
non-metadata examples where you get some data source, it has a bunch of numbers in it, but
what actually do these numbers mean? And how do you go from like, oh yeah, they told you
some stuff to understanding where there might be errors in the numbers or where it might
mean different things for different companies or different records or different examples
or whatever. Just to get a sense of how the kind of domain-specific stuff shows up beyond
the traditional metadata problems and into the wilder world of the different kinds of data
you encounter.

Eric

So we talked about the satellite photos of Walmart parking lots. And…

Ron

By the way, it’s such an old example. People used to talk about when people talk about the
classic example of does it count as insider trading if you’re flying in a plane and you
look down and I guess you see something like this. Is that actually a good one?

Eric

I don’t think so. I might get a bunch of LinkedIn messages from vendors after this saying,
“You’re totally wrong. I have these great photos of parking lots that I’d like to sell
you.” One problem is that, I don’t know, it’s kind of annoying. You have to take a lot of
photos of a lot of parking lots. It’s noisy. Maybe you get not that many photos per store
per day or week. Walmart has 20% of its shopping online. Other companies have more and
parking lots are not going to help you when measuring the behaviors of New York City
shoppers. And it’s also just really indirect. The thing you’re getting at is how many
people showed up, which is different from how much they’re spending. And you kind of think
from first principles, who knows what people are spending at Walmart stores? Well, Walmart
does, but they’re not going to tell you until the end of the quarter. Then the consumer
do. So I don’t know, you can ask them.

Ron

Although one by one, it’s going to take a while.

Eric

Yeah, it’s going to take a while but their bank knows. The bank that gave them that credit
card or the Visa or MasterCard network or the company that provides the plumbing to a host
of credit unions, for their credit and debit card programs, they know. And maybe they’re
willing to share anonymized or aggregated statistics about what spend they’re seeing. And
so you get some information about the transactions that some panel of credit cards are
making. And then where do you go from there? It’s not a random sample, all consumer
transaction in the United States. Transactions belonging to one credit card program. Maybe
the people who shop and have cards from credit unions are different from the transactions
from people who have a Chase Sapphire Reserve. Maybe the demographics of the panel are
just not the same as the broader United States. Maybe people drop in or drop out of the
panel. And if there are more consumers in the sample, does that mean that people are
spending more at Walmart or does it mean there are more consumers in the sample? And so
there are interesting modeling questions about, well, we have this information and how do
we make good predictions based on it adjusting for all of those factors?

Ron

And is that, trying to model out and adjust and maybe cross-compare different sources, is
that part of the data engineering work or is that part of what happens on the trading desk
after you get the cleaned up data put in front of you?

Point-in-time data and vendor revisions (01:01:30)

Eric

It’s a mix of the two, I think. But some of this really just does happen on the trading
desk. But I think the groundwork for doing all of this comes from a deep understanding of
how these data sets work and what information they provide you when, which the data
engineer typically builds up a good understanding of.

Ron

One thing I’d worry about, you mentioned there’s all this aggregation and anonymization
that’s done by the upstream vendors. You could imagine that could be done wrong or just
done in ways that introduces weird biases into the data that’s hard for you to see. Is
that a problem that you guys end up having to wrestle with?

Eric

Oh, I mean, so yes, vendors do weird things with their data all the time. Sometimes
they’ll have data missing. Sometimes they will say we compute this column one way and then
later tell you, whoops, made a mistake. All those values were wrong. Here’s what you
should have used instead. Sometimes associating a transaction with the stock of the, I
don’t know, the merchant is difficult and they improve these taggings over time. So
sometimes they’ll say, these transactions that we said were one thing are actually from
this other company or other brand.

Ron

And one thing that shows up if you have this issue where they’re going back and fixing
stuff in the past is there’s all these causality questions, right?

Eric

Right. On one hand, isn’t that helpful? They’re fixing the dataset.

Ron

Yeah, it was wrong. Now it’s right.

Eric

It was wrong, now it’s right. On the other hand, if you are doing a study at a firm like
Jane Street and you’re trying to figure out if I had been subscribing to this dataset,
would I be able to do good trades? Should I purchase the data set? If you’re trying to
make that decision and you are looking at the data that is not actually what you would’ve
received, but instead the corrected, more accurate version later, you’re not actually
studying what trades you would’ve done if you’ve been subscribing to the data set. You’re
simulating what you would’ve done if you had a time machine.

Ron

Right. Although it’s subtle. It depends on the nature of the correction. There’s a
question of in some sense, what could have been known at the time? And also what does it
mean for what could have been known in the future? There could be some data set where the
underlying data has real information and then they correct a completely mechanical thing
and then it’s okay. But it’s very easy when you’re doing that thing to smuggle information
into the past and it becomes very subtle. Whereas if you just timestamp what you had at
the time, then you know, well, at least it was definitely possible to have it at the time
because at the time I had it.

Eric

Yes. So what we love is when vendors say, this is exactly what I delivered at this moment
in time and here’s the corrected version that I delivered at this other point in time. And
not everyone does that. And so what we try to do is save all the data that we have access
to along with the time we received it so that no matter what transformations we do later,
we can always reconstruct what we would’ve known when.

Ron

Right. And no matter what the vendor does with their timestamps, we at least always
capture our timestamps of when we got it. Which by the way, is a very close analogy of
what we do with market data. Market data also comes with timestamps from the exchange and
we look at them with a certain amount of suspicion because all sorts of weird stuff can
happen. You can have some weird clock synchronization. The times can be off in various
ways, but we capture stuff when it lands on our network. And again, there’s still
information in their timestamps, but there’s a way in which we trust ours more than we
trust theirs.

Eric

Yeah. And knowing, okay, I received this packet at this nanosecond in time gives us more
confidence making decisions based on our historical studies than I received this packet at
about this moment in time. Yeah.

What AI changes about data work (01:06:05)

Ron

So to switch gears for a sec, one thing that has changed a lot in the last handful of
years, in fact, a lot of that change overlapped with a period of building up the Alt Data
team is, boy golly has AI moved a lot. And I think there’s kind of two different ways
within the Jane Street context where it’s changed. One is we have a lot more ML models,
neural net models that are being used as part of the trading process for consuming data
and transforming it. And then also we have these super smart LLMs that are useful
productivity tools. And I feel like both of these have lots of potential to change the alt
data process. And I’m kind of curious how the impact of those has landed along the last
few years.

Eric

So I think there are two kinds of impacts of AI here. One is that we have better models
for consuming this data and making predictions about the world, finding patterns. And that
means that the value of all of our data, of good quality data sets has just gone up. And
with LMs in particular, it’s easier to make use of text data to extract information or
features from text that would’ve been manual, annoying, impractical, a nest of Reg X’s
beforehand.

Ron

Yeah. They’re an amazing tool for extracting structured data from unstructured text.

Eric

Yeah.

Ron

Although also there’s a huge causality problem because if you use a really up-to-date LLM
that knows stuff about old data and trying to use it to futurize some old data, you’re
going to get very confusing things happen because the LLM is smart and knows things about
the future then.

Eric

Yeah. The LLM knows what happened to Enron. The LLM training data, maybe it includes the
financial statement or a future one. So that presents some difficulties. So then there’s
AI as a tool where a lot of the same trends and limitations that you see in software
engineering also hide to data engineering. They make it easier to produce code to do
analyses. And in the hands of good data engineers who know what they’re trying to get from
these tools and can tell whether the results are good or bad, they’re really helpful. And
our data engineers use LLMs. Also, they make it easier than ever to generate bad code.

Ron

Right. Never has the gap between merely doing something and doing something well been
larger in terms of cost. It’s so easy to just do something, but sometimes the results are
very bad.

Eric

Yeah. And it’s easy to do something and think I have solved the problem when in fact you
have failed to understand the problem.

Ron

So you have the normal ups and downs of using AI tools. They’re amazing and also they have
lots of pitfalls. And then you talked about AI as a kind of feature extraction, but
there’s also neural nets as models, as new ways of extracting value out of the data that
you get. Has that changed the process? Has it changed the value of having alternative
data? Has it changed the pitfalls of using it?

Eric

It certainly changed the value of having data alternative or otherwise. It’s generally
more valuable. Maybe some shapes and quantities of data are more amenable to these models
than others.

Ron

So one thing I’d wonder about is the value of some of the kind of what in other contexts
we’d call feature engineering. I think there’s the whole bitter lesson idea that lots of
ways that you try and express priors into the data itself or the shape of the model or
whatever maybe become less useful as the models get bigger and more powerful and stuff
because some of the regularization and futurization can be done inside of the model. So
there’s that. And then there’s also a question of just in general, how much data cleaning
and data preparation, is that more useful in a neural net context? Is it less?

Eric

I think the value of cleaning the data is greater. I think, I don’t know, if your data is
not point in time and secretly leaking information from the future into data that should
be in the past, these stronger models are going to be much better at picking up on those
effects that are not actually tradable. I think there are certain kinds of outliers and
weird patches of data that some models handle well and other models handle poorly in their
training process and getting the quality right is more important for those models. So
internally the models will be able to do more. You will have to handcraft features less
and it will be better at figuring out which ones are important or not. But the value of
getting the data that you do pass and write is pretty high. And I think then it becomes
like, well, are LLMs with the skills and harness and whatever we build about them, going
to be able to completely automate that? I think that’s similar to will we replace all
software engineers with LLMs too.

Ron

Right. The current horizon and at least what you can see me, it seems like an enormous
amount of human judgment is incredibly important. In some ways it feels like human
judgment just gets more important as it becomes the thing that unlocks. You can do all the
stuff really fast if you can figure out if it’s good. So the verification bottleneck
becomes really important and this is a very critically human part of that at the moment.

Eric

And taste for what should be built well.

Ron

Absolutely.

Eric

Yeah.

Build vs. buy (01:12:47)

Ron

Speaking of what should be built, I feel like the alt data world here has been a kind of
Jane Street flavored software engineering adventure in that, boy, we’ve made a lot of our
own exciting custom stuff. And we’ve also used some external outside world stuff. And I’m
curious how you guys have thought about and navigated the question of where does it make
sense to buy some external product for helping to manage this? After all, we’re not the
only people who manage these kind of alt data pipelines and where we have decided to make
our own things and has that been good? Has it been bad? How do you think about the choices
there?

Eric

Yeah. Some of our software stack is very much pulled from the rest of the world. A lot of
data engineers outside Jane Street use dbt, which stands for data build tool. Data build
tool is a tool for describing and orchestrating transformations in your data warehouse,
usually using SQL queries, but in a code reviewable, testable, composable, good software
engineering practices way.

Ron

Sounds great.

Eric

So I have seen 300 line Postgres views and functions in my time at Jane Street and we
don’t want any of that. dbt lets you break down the data transformation problem into
smaller components and test the properties of the data at each stage so that you can rely
on it. Our data warehouse’s query engine is Trino. There are lots of Python tools for
processing tabular data. But other things we do build ourself, where if we were starting
from scratch and were entirely cloud-based, maybe we would do something more off the
shelf. But one thing that is pretty cool is that Jane Street is good at building and
operating on-prem data centers and we had to be in order to run low latency trading
systems before we were doing any of that alternative data stuff.

Ron

That’s right. And we need our own data centers in part for the kind of physical location
thing where you need to have your boxes close to the exchange. And also just some of the
underlying abstractions like clouds, no good at giving you multicast. You can’t easily
deploy FPGAs. There’s all sorts of things that you want in terms of control of the
physical architecture that you get in your own data center that you just can’t get in the
cloud. And the cloud gives you a bunch of other benefits. And these days we do a lot of
both.

Eric

Right. If you do have the ability to do things well on-prem, solution that works maybe not
the one that you would use if you were just using BigQuery or Snowflake or what have you.

Ron

Right. And I guess part of this came up in previous one of these conversations was we
built our own data warehouse. We have the Superstore. And we didn’t build it for alt data,
or at least not primarily for alt data, but that’s a tool that alt data now uses.

Eric

Yes. And it’s right having all of our data in one place and being able to handle the
volumes of trading data and other data that we use. It’s useful for being able to join it
to all of our other services internally. And the cost model is different. I don’t want to
imagine how much we would spend in credits or slots if all of the queries that we are
running now were built in a cloud warehouse.

Ron

So why is that? How is the cloud cost model different from the kind of cost model that we
get from this thing that we built ourselves?

Eric

So the cloud cost model will be based on either the amount of data you read or the amount
of time in their units of compute they use. And what we can do is just think about the
cost of acquiring the hardware and operating the hardware, which all in all is
significantly lower. They have large gross margins.

Ron

Is it that the overall margins are large or is it more that the incremental cost model -

Eric

You’re also not thinking about the cost of trying this one new thing, this one new query.

Ron

And if you just take the things that you get from cloud vendors and say, let’s look at
those prices and then apply it to our workloads, you’d be like, “Wow, I could get a lot of
hardware for that cost.” So just the way the math and practice works out is that it would
incentivize us to spend a lot of time figuring out how to optimize and do less work on the
system than it does when we actually go out and buy the physical hardware. So economic
theory and architecture aside, it’s just like that’s how the pricing model seems to work.

Eric

Yeah. If we were using one of these other products, we would spend a tremendous amount of
time optimizing our spend and trying to shape our workloads to fit their cost model. And
we do think about the performance of Trino and our data warehouse. We end up spending less
time on that.

Ron

Right. Because overall the costs in fact are lower.

Eric

Yeah.

Hiring data engineers (01:18:44)

Ron

Makes sense. So another thing I think is maybe you should talk about is we went from in
‘23, one data engineer to now more than 20 data engineers. And it sounds like we’re
continuing and are eagerly hiring.

Eric

Love to hire more.

Ron

And so I’m curious, what makes a good data engineer? What are you looking for when you’re
trying to hire someone? And then how do we find them?

Eric

Yeah. So the most important characteristics I think are curiosity and a good investigative
process. As part of the job, you’ll be learning about some new domain, some industry, some
kind of data, some kind of trading. And also you will have messy, unfamiliar data that is
useful, but also has lots of embedded problems in it. And I think to succeed, you have to
enjoy learning about all these new things And you have to enjoy learning about these new
things. You have to enjoy getting into the details. You have to be careful and think about
what you know and what you don’t yet know and how you would support going from point A to
point B. I think people with science or social science backgrounds who do work with messy
real world data and try to make sense of it are well suited to this. We also look for
engineering skills. I think the systems complexity of what data engineers are doing is
lower than much of what we ask our software engineers to do, but the data and business
complexity is still very high. Data pipelines are code.

Ron

You still want them to be good code.

Eric

They’re still software. You want them to be good code. You want them to be clear, correct,
maintainable. And we look for that too. And where do we find data engineers? Some of them
have worked in the financial industry before. Some of them are people who are the data
person at their small or mid-sized startup where they had to understand the data and the
business context and deal with its messiness because there were only so many other people
around to do that who also have developed good software engineering skills.

Ron

And so are you mostly looking for people who essentially have data wrangling experience as
a thing they’ve done already professionally?

Eric

Usually, though that doesn’t have to be at a company. It can be as part of research of
doing science or some other way. All of the people we’ve hired so far have been
experienced hires who were doing some thing beforehand. Next year we’re hoping to venture
into hiring interns. We started talking in 2025 about interviewing in 2026 for an
internship that runs in the summer of 2027 for people who start in 2028 after graduating
from school probably and are really ramped up and doing useful work in 2029.

Ron

Right.

Eric

Just long-term planning. And I think we’re looking for people who care about the data
first and maybe they have good engineering skills now, maybe they have the potential to
after a bunch of training.

Ron

Right, but the kind of excitement about digging into the data is the primary thing you’re
looking for.

Eric

Yeah. Well, on the other hand, there are people who work with a lot of data and are like,
“I am excited about building fancy models and neural networks,” or about building scalable
systems, the ML or the software engineering parts of it. And we want those people at Jane
Street too, but not for this role.

Ron

Got it. And then to say the interview side, you want to find people who are excited about
and have a good taste about how to think about and dig into data. How do you use an
interview to sus that out?

Eric

It’s hard. We have a few data investigation interviews or data wrangling interviews where
we give them some unfamiliar data set and they investigate and build some model of how it
works and do something with it. Seeing how someone approaches that problem. Are they
careful and detail oriented and do they think about what they know, what assumptions
they’re making, how they would test those assumptions? Or do they write a bunch of code
and say, “Hopefully this works, but I’m not sure.”

Ron

Right. And once again, rounding back to engaging with the real world underneath the data
and trying to actually think about what’s going on and seeing if that affects what you
should be doing.

Eric

Yeah.

Ron

Awesome. All right. Well, maybe that’s a good place to end it.

Eric

Yeah.

Ron

Thanks for joining me.

Eric

Thanks, Ron.

Ron

You’ll find a complete transcript of the episode along with show notes and links at
signalsandthreads.com.

TECH TALKS

Watch Tech Talks 

TECH BLOG

Read The Tech Blog 

JANE STREET TECH

Learn More 

JOIN OUR TEAM

Apply 

© Copyright 2020- Jane Street Group, LLC. All rights reserved.

Jane Street and the concentric circle mark are registered trademarks of Jane Street.

    Ad and Cookie Policy
      |  
    Privacy Policy

Jane Street is an Equal Opportunity Employer