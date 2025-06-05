ThisBuild / semanticdbVersion := "4.5.9"

ThisBuild / scalaVersion := "2.13.8"
ThisBuild / version := "0.1.0-SNAPSHOT"
ThisBuild / organization := "vn.fpt"
ThisBuild / organizationName := "fpt"
ThisBuild / pushRemoteCacheTo := Some(
  MavenCache("local-cache", file("sbt-cache/remote-cache"))
)
ThisBuild / scalacOptions := Seq(
  "-Xsource:3",
  "-Wunused:imports",
  "-Wunused:implicits",
  "-Wunused:patvars",
  "-Wunused:privates",
  "-Wunused:locals",
  "-deprecation"
)

ThisBuild / scalafixDependencies += "com.github.liancheng" %% "organize-imports" % "0.6.0"
ThisBuild / semanticdbVersion := scalafixSemanticdb.revision
ThisBuild / semanticdbEnabled := true

lazy val tapirVersion = "1.2.9"
lazy val akkaVersion = "2.8.2"
lazy val akkaHttpVersion = "10.2.10"
lazy val slickVersion = "3.3.3"
lazy val postgresqlVersion = "42.4.2"
lazy val slickPgVersion = "0.20.4"
lazy val enumeratumVersion = "1.7.0"
lazy val kebsVersion = "1.9.4"
lazy val logbackClassicVersion = "1.2.11"
lazy val chimneyVersion = "0.6.2"
lazy val scalaLoggingVersion = "3.9.5"
lazy val SttpVersion = "3.7.4"

lazy val datasharing = (project in file("."))
  .settings(
    name := "Test API",
    maintainer := "binhln@fpt.com",
    libraryDependencies ++= Seq(
      "com.typesafe.akka" %% "akka-actor-typed" % akkaVersion,
      "com.typesafe.akka" %% "akka-stream" % akkaVersion,
      "com.typesafe.akka" %% "akka-http" % akkaHttpVersion,
      "com.typesafe.akka" %% "akka-http-spray-json" % akkaHttpVersion,
      "com.typesafe.slick" %% "slick" % slickVersion,
      "com.typesafe.slick" %% "slick-hikaricp" % slickVersion,
      "com.typesafe.scala-logging" %% "scala-logging" % scalaLoggingVersion,
      "ch.qos.logback" % "logback-classic" % logbackClassicVersion,
      "org.postgresql" % "postgresql" % postgresqlVersion,
      "com.github.tminglei" %% "slick-pg" % slickPgVersion,
      "com.github.tminglei" %% "slick-pg_spray-json" % slickPgVersion,
      "com.softwaremill.sttp.tapir" %% "tapir-core" % tapirVersion,
      "com.softwaremill.sttp.tapir" %% "tapir-akka-http-server" % tapirVersion,
      "com.softwaremill.sttp.tapir" %% "tapir-json-spray" % tapirVersion,
      "com.softwaremill.sttp.tapir" %% "tapir-swagger-ui-bundle" % tapirVersion,
      "com.softwaremill.sttp.tapir" %% "tapir-enumeratum" % tapirVersion,
      "com.softwaremill.sttp.client3" %% "core" % SttpVersion,
      "com.softwaremill.sttp.client3" %% "akka-http-backend" % SttpVersion exclude ("com.typesafe.akka", "akka-http"),
      "com.softwaremill.sttp.client3" %% "spray-json" % SttpVersion exclude("io.spray", "spray-json"),
      "com.softwaremill.sttp.client3" %% "slf4j-backend" % SttpVersion,
      "com.beachape" %% "enumeratum" % enumeratumVersion,
      "com.beachape" %% "enumeratum-slick" % enumeratumVersion,
      "pl.iterators" %% "kebs-spray-json" % kebsVersion,
      "pl.iterators" %% "kebs-slick" % kebsVersion,
      "io.scalaland" %% "chimney" % chimneyVersion,
      "org.scalameta" %% "munit" % "0.7.29" % Test,
      "com.amazonaws" % "aws-java-sdk" % "1.12.315" excludeAll(ExclusionRule(organization = "org.slf4j")),
      "org.apache.tika" % "tika-core" % "2.5.0" excludeAll(ExclusionRule(organization="org.slf4j")),
      "org.typelevel" %% "cats-effect" % "3.4.6",
      "com.softwaremill.retry" %% "retry" % "0.3.6",
      "com.norbitltd" %% "spoiwo" % "2.2.1"
    ),
    Universal / packageName := "test-api-data-sharing",
    Universal / javaOptions ++= Seq(
      "-Djdk.internal.httpclient.disableHostnameVerification=true",
      "-Dhttp.nonProxyHosts=*.bigdata.local|localhost|*.cadshouse.fpt.vn"),
  ).enablePlugins(JavaAppPackaging)
