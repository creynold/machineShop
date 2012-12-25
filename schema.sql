drop table if exists schedule;
create table schedule (
  id integer primary key autoincrement,
  username string not null,
  time string not null
);

drop table if exists users;
create table users (
  id integer primary key autoincrement,
  username string not null,
  cell_number integer,
  cell_provider string,
  looking boolean not null,
  is_admin boolean not null
);
